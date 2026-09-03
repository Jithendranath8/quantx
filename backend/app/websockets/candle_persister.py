"""
QuantX — Candle Persistence from the Live Stream.

Writes closed candles to the database as they arrive, so stored history is
current rather than however far behind the last REST backfill left it.

Before this, the stream republished ticks to Redis for the live price display
but never wrote a row. The candles table was only ever advanced by the
ten-minute sync job, so every chart and every backtest ran on data that could
be ten minutes stale while the price ticker beside it was live.

Only *closed* candles are stored. Persisting an in-progress bar would write a
partial high/low/volume that the next tick immediately contradicts.
"""

import asyncio
import contextlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert

from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.models.market_data import Candle

logger = get_logger(__name__)

# Closed candles arrive in bursts: every configured symbol closes its 1m bar in
# the same second. Buffering turns N transactions into one.
FLUSH_INTERVAL_SECONDS = 2.0
MAX_BUFFER = 500


class CandlePersister:
    """Buffers closed candles and upserts them in batches."""

    def __init__(self, session_factory: Callable[[], Any] | None = None) -> None:
        """
        Args:
            session_factory: Overrides where rows are written. The default
                resolves lazily so the engine is created inside whichever loop
                the stream runs on.
        """
        self._session_factory = session_factory
        # Keyed by (symbol, timeframe, open_time) so a repeated close for the
        # same bar collapses instead of queueing twice.
        self._pending: dict[tuple[str, str, int], dict] = {}
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self.persisted_count = 0
        self.failed_flushes = 0

    async def start(self) -> None:
        """Begin the periodic flush loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._flush_loop(), name="candle-persister")
        logger.info("candle_persister_started")

    async def stop(self) -> None:
        """Flush anything buffered, then stop."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.flush()
        logger.info("candle_persister_stopped", persisted=self.persisted_count)

    async def offer(self, event: dict) -> None:
        """Queue a normalized kline event if it represents a closed bar."""
        if event.get("event_type") != "kline" or not event.get("is_final"):
            return

        open_time = event.get("open_time")
        symbol = event.get("symbol")
        interval = event.get("interval")
        if not (open_time and symbol and interval):
            return

        row = {
            "symbol": symbol,
            "timeframe": interval,
            "timestamp": datetime.fromtimestamp(int(open_time) / 1000, tz=UTC),
            "open": event["open"],
            "high": event["high"],
            "low": event["low"],
            "close": event["close"],
            "volume": event["volume"],
            "close_time": datetime.fromtimestamp(
                int(event.get("close_time") or open_time) / 1000, tz=UTC
            ),
            "quote_volume": event.get("quote_volume", 0.0),
            "trades_count": event.get("trades_count", 0),
            "is_closed": True,
        }

        async with self._lock:
            self._pending[(symbol, interval, int(open_time))] = row
            over_capacity = len(self._pending) >= MAX_BUFFER

        # A burst larger than the buffer flushes immediately rather than
        # growing without bound between ticks.
        if over_capacity:
            await self.flush()

    async def flush(self) -> int:
        """Write buffered candles. Returns how many rows were upserted."""
        async with self._lock:
            if not self._pending:
                return 0
            batch = list(self._pending.values())
            self._pending.clear()

        try:
            # Resolving the factory is inside the guard on purpose: creating
            # the engine can itself fail, and that must degrade quietly like
            # any other database problem rather than tear down the stream.
            factory = self._session_factory or get_session_factory()
            async with factory() as session:
                stmt = insert(Candle).values(batch)
                await session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["symbol", "timeframe", "timestamp"],
                        set_={
                            "open": stmt.excluded.open,
                            "high": stmt.excluded.high,
                            "low": stmt.excluded.low,
                            "close": stmt.excluded.close,
                            "volume": stmt.excluded.volume,
                            "close_time": stmt.excluded.close_time,
                            "quote_volume": stmt.excluded.quote_volume,
                            "trades_count": stmt.excluded.trades_count,
                        },
                    )
                )
                await session.commit()
        except Exception as exc:
            # A database blip must not kill the stream. The ten-minute REST
            # sync backfills whatever was dropped here.
            self.failed_flushes += 1
            logger.error("candle_persist_failed", rows=len(batch), error=str(exc))
            return 0

        self.persisted_count += len(batch)
        logger.debug("candles_persisted", rows=len(batch), total=self.persisted_count)
        return len(batch)

    async def _flush_loop(self) -> None:
        """Flush on a fixed cadence for as long as the stream runs."""
        while self._running:
            try:
                await asyncio.sleep(FLUSH_INTERVAL_SECONDS)
                await self.flush()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("candle_persister_loop_error", error=str(exc))
