"""
QuantX — Unit Tests for market data normalization, caching, and channel naming.
"""

import json
import time

import pytest

from app.websockets import channels
from app.websockets.binance_stream import BinanceStreamManager
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

    def test_stream_url_covers_every_symbol_and_interval(self) -> None:
        """Combined streams request all configured pairs at once."""
        manager = BinanceStreamManager(symbols=["BTCUSDT", "ETHUSDT"], intervals=["1m", "5m"])
        url = manager.stream_url
        for expected in ("btcusdt@kline_1m", "btcusdt@kline_5m", "ethusdt@kline_1m"):
            assert expected in url

    @pytest.mark.asyncio
    async def test_handle_message_publishes_to_the_matching_channel(self) -> None:
        """A kline is republished on the channel the gateway subscribes to."""
        published: list[tuple[str, str]] = []

        class FakeRedis:
            async def publish(self, channel: str, payload: str) -> None:
                published.append((channel, payload))

        manager = BinanceStreamManager(symbols=["BTCUSDT"], intervals=["1m"])
        await manager._handle_message(FakeRedis(), json.dumps({"data": KLINE_EVENT}))

        assert len(published) == 1
        channel, payload = published[0]
        assert channel == channels.kline_channel("BTCUSDT", "1m")
        assert json.loads(payload)["close"] == 50250.0
        assert manager.metrics.messages_received == 1

    @pytest.mark.asyncio
    async def test_unparseable_message_is_ignored(self) -> None:
        """Malformed JSON does not kill the stream."""
        class FakeRedis:
            async def publish(self, channel: str, payload: str) -> None:
                raise AssertionError("should not publish")

        manager = BinanceStreamManager(symbols=["BTCUSDT"])
        await manager._handle_message(FakeRedis(), "not json")

    @pytest.mark.asyncio
    async def test_invalid_candle_is_not_published(self) -> None:
        """A candle that fails validation is dropped rather than forwarded."""
        class FakeRedis:
            async def publish(self, channel: str, payload: str) -> None:
                raise AssertionError("should not publish")

        broken = {**KLINE_EVENT, "k": {**KLINE_EVENT["k"], "h": "1.0", "l": "9999.0"}}
        manager = BinanceStreamManager(symbols=["BTCUSDT"])
        await manager._handle_message(FakeRedis(), json.dumps(broken))
