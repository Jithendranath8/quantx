"""
QuantX — Single-owner election for the market data stream.

Uvicorn runs ``BACKEND_WORKERS`` processes and FastAPI's lifespan fires in every
one of them. Starting the Binance stream directly from the lifespan therefore
opened one upstream connection *per worker*: four sockets against Binance's
connection limits, four copies of every tick published to Redis, and four
writers upserting the same candle rows. This module makes exactly one worker
the owner.

Ownership is a Redis key held under a TTL. The owner renews it while it lives;
if the owner process dies, the key expires and a follower takes over within
``LOCK_TTL_SECONDS``. Renewal and release are compare-and-swap against the
owner token so a worker that stalled past its TTL can never clobber the lock a
successor has already taken.
"""

import asyncio
import contextlib
import os
import uuid
from collections.abc import Awaitable, Callable

from app.core.logging import get_logger
from app.core.redis import get_redis_client

logger = get_logger(__name__)

LOCK_KEY = "quantx:stream:owner"
LOCK_TTL_SECONDS = 30
RENEW_INTERVAL_SECONDS = 10.0
# How often a follower re-checks for a vacant lock. Well under the TTL so a
# dead owner is replaced promptly rather than after a full extra cycle.
POLL_INTERVAL_SECONDS = 5.0

# Renew only if we still hold the lock. A plain EXPIRE would let a stalled
# worker extend a lock that has already passed to someone else.
_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""

_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class StreamLeader:
    """Runs ``start``/``stop`` callbacks only while this process owns the lock."""

    def __init__(
        self,
        on_acquire: Callable[[], Awaitable[None]],
        on_release: Callable[[], Awaitable[None]],
        on_heartbeat: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._on_acquire = on_acquire
        self._on_release = on_release
        # Called on each successful renewal so the owner can publish metrics
        # that non-owner workers have no way to observe locally.
        self._on_heartbeat = on_heartbeat
        # Identifies this process. The pid alone is not unique across
        # containers, so pair it with a random token.
        self.token = f"{os.getpid()}:{uuid.uuid4().hex}"
        self.is_leader = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Begin campaigning for ownership in the background."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop campaigning, release the lock, and stop the stream if leading."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self.is_leader:
            self.is_leader = False
            with contextlib.suppress(Exception):
                await self._on_release()
        await self._release()

    async def _acquire(self) -> bool:
        redis = await get_redis_client()
        return bool(await redis.set(LOCK_KEY, self.token, nx=True, ex=LOCK_TTL_SECONDS))

    async def _renew(self) -> bool:
        redis = await get_redis_client()
        result = await redis.eval(  # type: ignore[no-untyped-call]  # redis-py eval is untyped
            _RENEW_SCRIPT, 1, LOCK_KEY, self.token, LOCK_TTL_SECONDS
        )
        return bool(result)

    async def _release(self) -> None:
        with contextlib.suppress(Exception):
            redis = await get_redis_client()
            await redis.eval(  # type: ignore[no-untyped-call]  # redis-py eval is untyped
                _RELEASE_SCRIPT, 1, LOCK_KEY, self.token
            )

    async def _run(self) -> None:
        """Campaign forever: acquire, then renew; on loss, stop and re-campaign."""
        while True:
            try:
                if self.is_leader:
                    if await self._renew():
                        if self._on_heartbeat is not None:
                            with contextlib.suppress(Exception):
                                await self._on_heartbeat()
                        await asyncio.sleep(RENEW_INTERVAL_SECONDS)
                        continue
                    # Lost the lock (Redis restarted, or we stalled past the
                    # TTL). Shut the stream down before anything else claims it
                    # so we never run two ingestors at once.
                    logger.warning("stream_leadership_lost", token=self.token)
                    self.is_leader = False
                    with contextlib.suppress(Exception):
                        await self._on_release()
                    continue

                if await self._acquire():
                    logger.info("stream_leadership_acquired", token=self.token)
                    self.is_leader = True
                    await self._on_acquire()
                    continue

                await asyncio.sleep(POLL_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Redis blips must not kill the campaign loop; a follower that
                # stops polling would leave the stream permanently unowned once
                # the current leader exits.
                logger.error("stream_leader_error", error=str(exc))
                self.is_leader = False
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
