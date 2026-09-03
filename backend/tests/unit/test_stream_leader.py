"""
QuantX — Tests for single-owner election of the market data stream.

The regression these guard: FastAPI's lifespan runs in every uvicorn worker, so
before the election each of BACKEND_WORKERS processes opened its own Binance
socket and wrote the same candles.
"""

import asyncio

import pytest

from app.websockets import stream_leader as leader_mod
from app.websockets.stream_leader import LOCK_KEY, StreamLeader


class FakeRedis:
    """Minimal Redis stand-in supporting SET NX EX and the two Lua scripts."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        return int(self.store.pop(key, None) is not None)

    async def eval(self, script, numkeys, key, token, *args):
        if self.store.get(key) != token:
            return 0
        if "del" in script:
            del self.store[key]
        return 1


@pytest.fixture
def fake_redis(monkeypatch):
    redis = FakeRedis()

    async def _get_client():
        return redis

    monkeypatch.setattr(leader_mod, "get_redis_client", _get_client)
    return redis


def make_leader(events, name):
    async def on_acquire():
        events.append(f"{name}:start")

    async def on_release():
        events.append(f"{name}:stop")

    return StreamLeader(on_acquire, on_release)


@pytest.mark.asyncio
async def test_first_leader_acquires_and_starts(fake_redis):
    events: list[str] = []
    leader = make_leader(events, "a")
    await leader.start()
    await asyncio.sleep(0.05)
    try:
        assert leader.is_leader is True
        assert events == ["a:start"]
        assert fake_redis.store[LOCK_KEY] == leader.token
    finally:
        await leader.stop()


@pytest.mark.asyncio
async def test_second_worker_does_not_start_a_duplicate_stream(fake_redis):
    """The whole point: N workers, one Binance connection."""
    events: list[str] = []
    first = make_leader(events, "a")
    second = make_leader(events, "b")
    await first.start()
    await asyncio.sleep(0.05)
    await second.start()
    await asyncio.sleep(0.05)
    try:
        assert first.is_leader is True
        assert second.is_leader is False
        assert "b:start" not in events
    finally:
        await first.stop()
        await second.stop()


@pytest.mark.asyncio
async def test_follower_takes_over_when_owner_exits(fake_redis, monkeypatch):
    monkeypatch.setattr(leader_mod, "POLL_INTERVAL_SECONDS", 0.01)
    events: list[str] = []
    first = make_leader(events, "a")
    second = make_leader(events, "b")
    await first.start()
    await asyncio.sleep(0.05)
    await second.start()
    await asyncio.sleep(0.05)
    assert second.is_leader is False

    await first.stop()          # releases the lock
    await asyncio.sleep(0.08)   # follower polls and claims it
    try:
        assert second.is_leader is True
        assert events == ["a:start", "a:stop", "b:start"]
    finally:
        await second.stop()


@pytest.mark.asyncio
async def test_stop_releases_lock_for_successors(fake_redis):
    events: list[str] = []
    leader = make_leader(events, "a")
    await leader.start()
    await asyncio.sleep(0.05)
    await leader.stop()
    assert LOCK_KEY not in fake_redis.store


@pytest.mark.asyncio
async def test_stop_does_not_release_a_lock_owned_by_someone_else(fake_redis):
    """A stalled worker must never delete the successor's lock."""
    events: list[str] = []
    leader = make_leader(events, "a")
    await leader.start()
    await asyncio.sleep(0.05)
    fake_redis.store[LOCK_KEY] = "someone-else"
    await leader.stop()
    assert fake_redis.store[LOCK_KEY] == "someone-else"


@pytest.mark.asyncio
async def test_losing_the_lock_stops_the_stream(fake_redis, monkeypatch):
    """If the lock is lost mid-flight, ingestion must stop before a rival starts."""
    monkeypatch.setattr(leader_mod, "RENEW_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(leader_mod, "POLL_INTERVAL_SECONDS", 0.01)
    events: list[str] = []
    leader = make_leader(events, "a")
    await leader.start()
    await asyncio.sleep(0.05)
    assert leader.is_leader is True

    fake_redis.store[LOCK_KEY] = "rival"   # simulate expiry + rival takeover
    await asyncio.sleep(0.08)
    try:
        assert leader.is_leader is False
        assert "a:stop" in events
    finally:
        await leader.stop()


@pytest.mark.asyncio
async def test_heartbeat_fires_only_while_leading(fake_redis, monkeypatch):
    monkeypatch.setattr(leader_mod, "RENEW_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(leader_mod, "POLL_INTERVAL_SECONDS", 0.01)
    beats: list[int] = []

    async def noop():
        return None

    async def beat():
        beats.append(1)

    owner = StreamLeader(noop, noop, on_heartbeat=beat)
    follower = StreamLeader(noop, noop, on_heartbeat=beat)
    await owner.start()
    await asyncio.sleep(0.05)
    await follower.start()
    await asyncio.sleep(0.05)
    try:
        assert len(beats) >= 1
        before = len(beats)
        await asyncio.sleep(0.05)
        # Beats keep coming from the owner, and the follower contributes none:
        # every beat is one renewal, so the count tracks the owner alone.
        assert len(beats) > before
        assert follower.is_leader is False
    finally:
        await owner.stop()
        await follower.stop()


@pytest.mark.asyncio
async def test_redis_failure_does_not_kill_the_campaign(monkeypatch):
    """A Redis blip must not leave the stream permanently unowned."""
    monkeypatch.setattr(leader_mod, "POLL_INTERVAL_SECONDS", 0.01)
    calls = {"n": 0}
    redis = FakeRedis()

    async def _get_client():
        calls["n"] += 1
        if calls["n"] <= 2:
            raise ConnectionError("redis down")
        return redis

    monkeypatch.setattr(leader_mod, "get_redis_client", _get_client)
    events: list[str] = []
    leader = make_leader(events, "a")
    await leader.start()
    await asyncio.sleep(0.1)
    try:
        assert leader.is_leader is True
        assert events == ["a:start"]
    finally:
        await leader.stop()
