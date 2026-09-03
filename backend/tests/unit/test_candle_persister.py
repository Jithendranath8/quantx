"""
QuantX — Unit Tests for live candle persistence.

The stream republished ticks to Redis for the live price display but never
wrote a row. The candles table only advanced when the ten-minute REST sync ran,
so every chart and backtest used data up to ten minutes stale while the price
ticker beside it was live.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data import Candle
from app.websockets.binance_stream import BinanceStreamManager
from app.websockets.candle_persister import CandlePersister
from app.websockets.market_data_engine import MarketDataNormalizer


class _SessionCtx:
    """Adapt the test session to the `async with factory()` protocol."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *exc: object) -> None:
        return None


def persister_for(session: AsyncSession) -> CandlePersister:
    """A persister writing into the test session."""
    return CandlePersister(session_factory=lambda: _SessionCtx(session))

BAR_OPEN_MS = int(datetime(2026, 9, 2, 15, 53, tzinfo=UTC).timestamp() * 1000)


def kline_event(is_final: bool, open_ms: int = BAR_OPEN_MS, interval: str = "1m") -> dict:
    """A normalized kline event as the stream produces one."""
    return MarketDataNormalizer.normalize_kline(
        {
            "E": open_ms + 59_000,
            "s": "BTCUSDT",
            "k": {
                "t": open_ms,
                "T": open_ms + 59_999,
                "s": "BTCUSDT",
                "i": interval,
                "o": "77500.00",
                "h": "77650.00",
                "l": "77450.00",
                "c": "77600.00",
                "v": "12.5",
                "q": "969500.0",
                "n": 842,
                "x": is_final,
            },
        }
    )


@pytest.mark.unit
class TestNormalizerCompleteness:
    """A persisted candle needs every NOT NULL column."""

    def test_kline_carries_the_columns_the_table_requires(self) -> None:
        """close_time, quote_volume and trade count come through."""
        event = kline_event(is_final=True)
        assert event["open_time"] == BAR_OPEN_MS
        assert event["close_time"] == BAR_OPEN_MS + 59_999
        assert event["quote_volume"] == pytest.approx(969500.0)
        assert event["trades_count"] == 842
        assert event["is_final"] is True


@pytest.mark.unit
class TestCandlePersister:
    """Buffering and upserting closed bars."""

    @pytest.mark.asyncio
    async def test_closed_candle_is_written(self, db_session: AsyncSession) -> None:
        """A closed bar reaches the table."""
        persister = persister_for(db_session)
        await persister.offer(kline_event(is_final=True))
        assert await persister.flush() == 1

        stored = (
            await db_session.execute(select(Candle).where(Candle.symbol == "BTCUSDT"))
        ).scalar_one()
        assert stored.timeframe == "1m"
        assert stored.close == pytest.approx(77600.0)
        assert stored.trades_count == 842
        assert stored.is_closed is True

    @pytest.mark.asyncio
    async def test_in_progress_candle_is_ignored(self, db_session: AsyncSession) -> None:
        """An open bar is not stored.

        Its high, low and volume are still moving; writing it would persist a
        partial bar that the next tick immediately contradicts.
        """
        persister = persister_for(db_session)
        await persister.offer(kline_event(is_final=False))
        assert await persister.flush() == 0

        count = (
            await db_session.execute(select(func.count()).select_from(Candle))
        ).scalar_one()
        assert count == 0

    @pytest.mark.asyncio
    async def test_repeated_close_for_one_bar_collapses(self, db_session: AsyncSession) -> None:
        """Binance can resend a final kline; it must not queue twice."""
        persister = persister_for(db_session)
        for _ in range(4):
            await persister.offer(kline_event(is_final=True))
        assert await persister.flush() == 1

    @pytest.mark.asyncio
    async def test_reflushing_the_same_bar_updates_rather_than_duplicates(
        self, db_session: AsyncSession
    ) -> None:
        """A later revision of the same bar overwrites it."""
        persister = persister_for(db_session)
        await persister.offer(kline_event(is_final=True))
        await persister.flush()

        revised = kline_event(is_final=True)
        revised["close"] = 77999.0
        await persister.offer(revised)
        await persister.flush()

        rows = list((await db_session.execute(select(Candle))).scalars().all())
        assert len(rows) == 1
        assert rows[0].close == pytest.approx(77999.0)

    @pytest.mark.asyncio
    async def test_multiple_timeframes_are_stored_separately(
        self, db_session: AsyncSession
    ) -> None:
        """Each timeframe is its own series, so all of them stay current."""
        persister = persister_for(db_session)
        for interval in ("1m", "5m", "1h", "1d"):
            await persister.offer(kline_event(is_final=True, interval=interval))
        assert await persister.flush() == 4

        stored = {
            r.timeframe
            for r in (await db_session.execute(select(Candle))).scalars().all()
        }
        assert stored == {"1m", "5m", "1h", "1d"}

    @pytest.mark.asyncio
    async def test_flush_with_nothing_buffered_is_a_noop(self) -> None:
        """An idle flush does not open a transaction."""
        assert await CandlePersister().flush() == 0

    @pytest.mark.asyncio
    async def test_a_database_failure_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A database blip must not kill the stream.

        The REST sync backfills whatever was dropped, so degrading quietly
        here is correct; propagating would tear down the subscription.
        """
        def explode() -> None:
            raise RuntimeError("connection pool exhausted")

        monkeypatch.setattr(
            "app.websockets.candle_persister.get_session_factory", explode
        )

        persister = CandlePersister()
        await persister.offer(kline_event(is_final=True))
        assert await persister.flush() == 0
        assert persister.failed_flushes == 1

    @pytest.mark.asyncio
    async def test_non_kline_events_are_ignored(self) -> None:
        """Trades and depth are not candles."""
        persister = CandlePersister()
        await persister.offer({"event_type": "trade", "symbol": "BTCUSDT", "price": 1.0})
        assert await persister.flush() == 0


@pytest.mark.unit
class TestStreamPersistsClosedBars:
    """The stream hands closed bars to the persister."""

    @pytest.mark.asyncio
    async def test_handle_message_offers_closed_candles(self) -> None:
        """A final kline off the wire is queued for storage."""
        import json

        class FakeRedis:
            async def publish(self, channel: str, payload: str) -> None:
                return None

        manager = BinanceStreamManager(symbols=["BTCUSDT"], intervals=["1m"])
        raw = {
            "E": BAR_OPEN_MS + 59_000, "s": "BTCUSDT",
            "k": {"t": BAR_OPEN_MS, "T": BAR_OPEN_MS + 59_999, "s": "BTCUSDT", "i": "1m",
                  "o": "77500", "h": "77650", "l": "77450", "c": "77600",
                  "v": "12.5", "q": "969500", "n": 842, "x": True},
        }
        await manager._handle_message(FakeRedis(), json.dumps({"data": raw}))

        assert len(manager.persister._pending) == 1

    @pytest.mark.asyncio
    async def test_handle_message_skips_open_candles(self) -> None:
        """An in-progress bar is published but not queued for storage."""
        import json

        class FakeRedis:
            async def publish(self, channel: str, payload: str) -> None:
                return None

        manager = BinanceStreamManager(symbols=["BTCUSDT"], intervals=["1m"])
        raw = {
            "E": BAR_OPEN_MS + 30_000, "s": "BTCUSDT",
            "k": {"t": BAR_OPEN_MS, "T": BAR_OPEN_MS + 59_999, "s": "BTCUSDT", "i": "1m",
                  "o": "77500", "h": "77650", "l": "77450", "c": "77600",
                  "v": "6.0", "q": "465000", "n": 400, "x": False},
        }
        await manager._handle_message(FakeRedis(), json.dumps({"data": raw}))

        assert manager.persister._pending == {}

    def test_stream_covers_every_configured_timeframe(self) -> None:
        """Streaming only 1m would leave every other timeframe stale."""
        from app.core.config import get_settings

        settings = get_settings()
        manager = BinanceStreamManager()
        url = manager.stream_url
        for timeframe in settings.market_timeframe_list:
            assert f"@kline_{timeframe}" in url, f"{timeframe} is not streamed"
