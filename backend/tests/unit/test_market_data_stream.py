"""
QuantX — Unit Tests for market data normalization, caching, and channel naming.
"""

import asyncio
import json
import time

import pytest

from app.websockets import channels
from app.websockets.binance_stream import BinanceStreamManager
from app.websockets.local_bus import QUEUE_MAXSIZE, LocalMarketBus, market_bus
from app.websockets.market_data_engine import (
    MarketDataCache,
    MarketDataMetrics,
    MarketDataNormalizer,
    MarketDataValidator,
)

KLINE_EVENT = {
    "e": "kline",
    "E": 1700000000000,
    "s": "BTCUSDT",
    "k": {
        "t": 1700000000000, "s": "BTCUSDT", "i": "1m",
        "o": "50000.0", "h": "50500.0", "l": "49800.0", "c": "50250.0",
        "v": "12.5", "x": True,
    },
}


@pytest.mark.unit
class TestChannelNaming:
    """Publisher and subscriber must derive channel names identically."""

    def test_publisher_channel_matches_subscriber_pattern(self) -> None:
        """A published kline channel matches the gateway's symbol pattern.

        The publisher used to write market:btcusdt:kline_1m while the gateway
        subscribed to market:BTCUSDT:*, so no message ever matched -- silently,
        with no error anywhere.
        """
        import fnmatch

        channel = channels.kline_channel("btcusdt", "1m")
        pattern = channels.symbol_pattern("BTCUSDT")
        assert fnmatch.fnmatch(channel, pattern)

    def test_casing_is_normalized(self) -> None:
        """Symbol casing cannot cause a mismatch."""
        assert channels.kline_channel("btcusdt", "1m") == channels.kline_channel("BTCUSDT", "1m")
        assert channels.symbol_pattern("btcusdt") == channels.symbol_pattern("BTCUSDT")

    def test_channel_for_event_dispatches_by_type(self) -> None:
        """Each event type maps to its own channel."""
        assert channels.channel_for_event("BTCUSDT", "kline", "5m").endswith("kline:5m")
        assert channels.channel_for_event("BTCUSDT", "trade").endswith(":trade")
        assert channels.channel_for_event("BTCUSDT", "depth").endswith(":depth")


@pytest.mark.unit
class TestNormalizer:
    """Raw Binance payloads become unified domain events."""

    def test_normalize_kline(self) -> None:
        """Kline fields are typed and renamed consistently."""
        event = MarketDataNormalizer.normalize_kline(KLINE_EVENT)
        assert event["event_type"] == "kline"
        assert event["symbol"] == "BTCUSDT"
        assert event["close"] == 50250.0
        assert event["is_final"] is True
        assert event["interval"] == "1m"

    def test_normalize_dispatches_on_shape(self) -> None:
        """The dispatcher recognises klines, trades, and depth."""
        assert MarketDataNormalizer.normalize(KLINE_EVENT)["event_type"] == "kline"
        assert MarketDataNormalizer.normalize(
            {"s": "BTCUSDT", "p": "50000", "q": "0.5", "m": False}
        )["event_type"] == "trade"
        assert MarketDataNormalizer.normalize(
            {"s": "BTCUSDT", "b": [["1", "2"]], "a": [["3", "4"]]}
        )["event_type"] == "depth"
        assert MarketDataNormalizer.normalize({"unknown": True}) is None


@pytest.mark.unit
class TestValidator:
    """Freshness and sanity checks."""

    def test_valid_candle_accepted(self) -> None:
        """A well-formed candle passes."""
        assert MarketDataValidator.validate_candle(
            {"open": 100, "high": 110, "low": 90, "close": 105}
        )

    @pytest.mark.parametrize(
        "candle",
        [
            {"open": 100, "high": 80, "low": 90, "close": 105},   # high < low
            {"open": 0, "high": 110, "low": 90, "close": 105},    # non-positive
            {"open": 100, "high": 110, "low": 90, "close": 200},  # close outside range
            {"open": 100, "high": 110},                            # missing fields
        ],
    )
    def test_invalid_candles_rejected(self, candle: dict) -> None:
        """Structurally impossible candles are rejected."""
        assert MarketDataValidator.validate_candle(candle) is False

    def test_staleness(self) -> None:
        """Old messages are flagged as stale."""
        now_ms = time.time() * 1000
        assert MarketDataValidator.is_stale(now_ms - 60_000, max_age_seconds=10) is True
        assert MarketDataValidator.is_stale(now_ms, max_age_seconds=10) is False


@pytest.mark.unit
class TestCache:
    """The latest-value cache is bounded."""

    def test_stores_and_reads_back(self) -> None:
        """Values round-trip, case-insensitively."""
        cache = MarketDataCache()
        cache.update_candle("btcusdt", {"close": 1.0})
        assert cache.get_candle("BTCUSDT") == {"close": 1.0}

    def test_evicts_beyond_capacity(self) -> None:
        """A symbol cap prevents unbounded growth in a long-lived process."""
        cache = MarketDataCache(max_symbols=3)
        for i in range(10):
            cache.update_candle(f"SYM{i}", {"close": i})
        assert cache.get_candle("SYM0") is None
        assert cache.get_candle("SYM9") == {"close": 9}

    def test_update_routes_by_event_type(self) -> None:
        """A normalized event lands in the right store."""
        cache = MarketDataCache()
        cache.update({"event_type": "trade", "symbol": "BTCUSDT", "price": 1.0})
        assert cache.get_trade("BTCUSDT") is not None
        assert cache.get_candle("BTCUSDT") is None


@pytest.mark.unit
class TestMetrics:
    """Connection health counters."""

    def test_age_is_infinite_before_first_event(self) -> None:
        """A stream that never received anything is infinitely stale."""
        assert MarketDataMetrics().age_seconds == float("inf")

    def test_observe_records_an_event(self) -> None:
        """Observing an event updates the counters."""
        metrics = MarketDataMetrics()
        metrics.observe(time.time() * 1000)
        assert metrics.messages_received == 1
        assert metrics.age_seconds < 1.0


@pytest.mark.unit
class TestStreamManager:
    """Stream URL construction and message handling."""

    def test_testnet_uses_the_stream_subdomain(self) -> None:
        """Testnet WebSockets live on stream.testnet.binance.vision.

        testnet.binance.vision serves the REST API and answers 404 to a
        WebSocket upgrade, which produced an endless reconnect loop that still
        reported itself as merely "RECONNECTING".
        """
        assert BinanceStreamManager.WS_TESTNET_URL.startswith(
            "wss://stream.testnet.binance.vision"
        )
        assert "//testnet.binance.vision" not in BinanceStreamManager.WS_TESTNET_URL

    def test_mainnet_url_is_the_combined_stream_endpoint(self) -> None:
        """Combined streams are served from /stream, not /ws."""
        assert BinanceStreamManager.WS_BASE_URL.endswith("/stream")

    def test_market_ws_defaults_to_the_geofree_public_mirror(self) -> None:
        """Live data uses the geo-free public mirror, not the thin testnet feed.

        The main stream host is geo-blocked from the same regions as the REST
        API, and the testnet feed stalls ("a few candles, then nothing"); the
        public mirror carries real mainnet ticks everywhere.
        """
        manager = BinanceStreamManager(symbols=["BTCUSDT"], intervals=["1m"])
        assert manager.base_url.endswith("/stream")
        assert "testnet" not in manager.base_url

    def test_stream_url_covers_every_symbol_and_interval(self) -> None:
        """Combined streams request all configured pairs at once."""
        manager = BinanceStreamManager(symbols=["BTCUSDT", "ETHUSDT"], intervals=["1m", "5m"])
        url = manager.stream_url
        for expected in ("btcusdt@kline_1m", "btcusdt@kline_5m", "ethusdt@kline_1m"):
            assert expected in url

    @pytest.mark.asyncio
    async def test_handle_message_fans_out_to_the_local_bus(self) -> None:
        """Single-worker (the default): a kline is delivered in-process, no Redis."""
        manager = BinanceStreamManager(symbols=["BTCUSDT"], intervals=["1m"])
        assert manager._single_worker

        async with market_bus.subscribe("BTCUSDT") as queue:
            # redis is unused on this path, so None is a valid argument.
            await manager._handle_message(None, json.dumps({"data": KLINE_EVENT}))
            payload = await asyncio.wait_for(queue.get(), timeout=1.0)

        assert json.loads(payload)["close"] == 50250.0
        assert manager.metrics.messages_received == 1

    @pytest.mark.asyncio
    async def test_handle_message_publishes_to_redis_in_multiworker(self) -> None:
        """Multi-worker: a kline is republished on the gateway's channel."""
        published: list[tuple[str, str]] = []

        class FakeRedis:
            async def publish(self, channel: str, payload: str) -> None:
                published.append((channel, payload))

        manager = BinanceStreamManager(symbols=["BTCUSDT"], intervals=["1m"])
        manager._single_worker = False
        await manager._handle_message(FakeRedis(), json.dumps({"data": KLINE_EVENT}))

        assert len(published) == 1
        channel, payload = published[0]
        assert channel == channels.kline_channel("BTCUSDT", "1m")
        assert json.loads(payload)["close"] == 50250.0
        assert manager.metrics.messages_received == 1

    @pytest.mark.asyncio
    async def test_unparseable_message_is_ignored(self) -> None:
        """Malformed JSON does not kill the stream (and never publishes)."""
        class FakeRedis:
            async def publish(self, channel: str, payload: str) -> None:
                raise AssertionError("should not publish")

        manager = BinanceStreamManager(symbols=["BTCUSDT"])
        manager._single_worker = False
        await manager._handle_message(FakeRedis(), "not json")

    @pytest.mark.asyncio
    async def test_invalid_candle_is_not_published(self) -> None:
        """A candle that fails validation is dropped rather than forwarded."""
        class FakeRedis:
            async def publish(self, channel: str, payload: str) -> None:
                raise AssertionError("should not publish")

        broken = {**KLINE_EVENT, "k": {**KLINE_EVENT["k"], "h": "1.0", "l": "9999.0"}}
        manager = BinanceStreamManager(symbols=["BTCUSDT"])
        manager._single_worker = False
        await manager._handle_message(FakeRedis(), json.dumps(broken))


@pytest.mark.unit
class TestLocalMarketBus:
    """In-process fan-out used on single-worker deployments."""

    @pytest.mark.asyncio
    async def test_delivers_to_every_subscriber_for_the_symbol(self) -> None:
        bus = LocalMarketBus()
        async with bus.subscribe("BTCUSDT") as a, bus.subscribe("BTCUSDT") as b:
            bus.publish("BTCUSDT", "tick")
            assert await asyncio.wait_for(a.get(), timeout=1.0) == "tick"
            assert await asyncio.wait_for(b.get(), timeout=1.0) == "tick"

    @pytest.mark.asyncio
    async def test_other_symbols_and_released_subscribers_get_nothing(self) -> None:
        bus = LocalMarketBus()
        async with bus.subscribe("ETHUSDT") as q:
            bus.publish("BTCUSDT", "tick")  # different symbol
            assert q.empty()
        # Context exited: the subscriber is gone, so the bus holds no queues.
        bus.publish("ETHUSDT", "tick")
        assert bus.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_full_queue_drops_oldest_rather_than_blocking(self) -> None:
        bus = LocalMarketBus()
        async with bus.subscribe("BTCUSDT") as q:
            for i in range(QUEUE_MAXSIZE + 5):
                bus.publish("BTCUSDT", str(i))
            # Never blocked; capped at the queue size, oldest evicted.
            assert q.qsize() == QUEUE_MAXSIZE
            assert await asyncio.wait_for(q.get(), timeout=1.0) == "5"


@pytest.mark.unit
class TestPartialDepth:
    """Partial-book-depth events (the live microstructure feed) carry no symbol
    of their own; it comes from the combined-stream name."""

    def test_symbol_is_taken_from_the_stream_name(self) -> None:
        ev = MarketDataNormalizer.normalize(
            {"lastUpdateId": 1, "bids": [["100.0", "2.0"]], "asks": [["101.0", "3.0"]]},
            "btcusdt@depth20@100ms",
        )
        assert ev is not None
        assert ev["event_type"] == "depth"
        assert ev["symbol"] == "BTCUSDT"
        assert ev["bids"] == [[100.0, 2.0]]
        assert ev["asks"] == [[101.0, 3.0]]

    def test_dropped_when_the_stream_name_is_missing(self) -> None:
        raw = {"bids": [["1", "1"]], "asks": [["2", "1"]]}
        assert MarketDataNormalizer.normalize(raw, "") is None

    def test_stream_url_subscribes_to_both_klines_and_depth(self) -> None:
        m = BinanceStreamManager(symbols=["BTCUSDT"], intervals=["1m"])
        assert "btcusdt@kline_1m" in m.stream_url
        assert "btcusdt@depth20@100ms" in m.stream_url
