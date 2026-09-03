"""
QuantX — Historical Market Data Downloader Service.

Fetches batch historical OHLCV data from Binance and performs efficient
PostgreSQL upserts.

Two things matter at scale here. Each batch is committed as it arrives rather
than accumulating a full year of candles in one transaction, and requests are
paced so a long backfill does not trip Binance's request-weight limit and get
the host IP banned.
"""

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.binance_client import BinanceClient, get_binance_client
from app.core.logging import get_logger
from app.models.market_data import Candle

logger = get_logger(__name__)

BATCH_LIMIT = 1000
# Binance allows 1200 request-weight per minute; klines cost 2. Pacing at
# ~5 req/s leaves ample headroom for the rest of the platform.
REQUEST_INTERVAL_SECONDS = 0.2
MAX_BATCHES = 5_000  # Hard stop so a bad interval cannot loop forever.


class HistoricalDownloaderService:
    """Downloader service for fetching and storing historical OHLCV data."""

    def __init__(self, session: AsyncSession, client: BinanceClient | None = None) -> None:
        self._session = session
        self._client = client or get_binance_client()

    async def download_history(
        self,
        symbol: str,
        timeframe: str,
        days: int = 30,
    ) -> int:
        """Download historical candles for a symbol and timeframe.

        Args:
            symbol: Trading symbol (e.g. 'BTCUSDT').
            timeframe: Candle interval (e.g. '1m', '5m', '1h').
            days: Historical lookback in days.

        Returns:
            Total count of candles ingested.
        """
        symbol = symbol.upper()
        end_time_ms = int(time.time() * 1000)
        start_time_ms = end_time_ms - (max(1, days) * 24 * 60 * 60 * 1000)

        total_saved = 0
        current_start = start_time_ms
        batches = 0

        while current_start < end_time_ms and batches < MAX_BATCHES:
            klines = await self._client.get_klines(
                symbol=symbol,
                interval=timeframe,
                start_time=current_start,
                end_time=end_time_ms,
                limit=BATCH_LIMIT,
            )
            if not klines:
                break

            saved = await self._save_klines(symbol, timeframe, klines)
            # Commit per batch: bounded transaction size, bounded memory, and
            # an interrupted backfill keeps everything already downloaded.
            await self._session.commit()

            total_saved += saved
            batches += 1

            last_open_time = int(klines[-1][0])
            if last_open_time <= current_start:
                break
            current_start = last_open_time + 1

            logger.info(
                "historical_klines_batch_ingested",
                symbol=symbol,
                timeframe=timeframe,
                batch_size=len(klines),
                total_saved=total_saved,
            )

            if len(klines) < BATCH_LIMIT:
                break
            await asyncio.sleep(REQUEST_INTERVAL_SECONDS)

        if batches >= MAX_BATCHES:
            logger.warning(
                "historical_download_batch_cap_reached",
                symbol=symbol,
                timeframe=timeframe,
                batches=batches,
            )

        return total_saved

    async def _save_klines(
        self,
        symbol: str,
        timeframe: str,
        klines: list[list[Any]],
    ) -> int:
        """Upsert one batch of klines on (symbol, timeframe, timestamp)."""
        candles_data = [
            {
                "symbol": symbol.upper(),
                "timeframe": timeframe,
                "timestamp": datetime.fromtimestamp(int(k[0]) / 1000, tz=UTC),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": datetime.fromtimestamp(int(k[6]) / 1000, tz=UTC),
                "quote_volume": float(k[7]),
                "trades_count": int(k[8]),
                "is_closed": True,
            }
            for k in klines
        ]

        if not candles_data:
            return 0

        stmt = insert(Candle).values(candles_data)
        stmt = stmt.on_conflict_do_update(
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
        await self._session.execute(stmt)
        return len(candles_data)
