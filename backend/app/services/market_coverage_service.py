"""
QuantX — Market Data Coverage.

Keeps stored candles complete across every symbol and timeframe the platform
advertises, and reports honestly on what is actually present.

The UI offers eight symbols and six timeframes. Without something that fills
all forty-eight combinations, most of them render as an empty table that is
indistinguishable from a broken query.

Lookback is per timeframe rather than a single "days" figure: a year of 1m
candles is half a million rows per symbol and nobody charts that far back at
minute resolution, while a year of daily candles is 365 rows and genuinely
useful.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.binance_client import BinanceClient, get_binance_client
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.market_data import Candle
from app.services.historical_downloader import HistoricalDownloaderService

logger = get_logger(__name__)

# How far back to keep each timeframe. Deep history where it is cheap and
# useful; shallow where it is expensive and nobody looks.
TIMEFRAME_LOOKBACK_DAYS: dict[str, int] = {
    "1m": 7,
    "3m": 14,
    "5m": 30,
    "15m": 60,
    "30m": 90,
    "1h": 365,
    "2h": 365,
    "4h": 365,
    "6h": 730,
    "12h": 730,
    "1d": 1095,
    "1w": 1825,
}
DEFAULT_LOOKBACK_DAYS = 90

# Approximate bar duration, used to judge whether a series is up to date.
TIMEFRAME_MINUTES: dict[str, int] = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720,
    "1d": 1440, "1w": 10080,
}

# A series is stale once it is this many bars behind...
STALE_BAR_MULTIPLE = 3

# ...but never sooner than the sync could plausibly have refreshed it. A 1m
# series topped up every ten minutes is legitimately several bars behind
# between runs; flagging that is noise, and noise trains people to ignore the
# flag that matters.
SYNC_INTERVAL_GRACE = 1.5

# Lookback for an incremental top-up of a series that already has data.
TOP_UP_DAYS = 2


def _scheduled_sync_interval_minutes() -> float:
    """How often the backfill actually runs, read from the beat schedule.

    Derived rather than hardcoded so the staleness threshold cannot drift out
    of step with the schedule that is supposed to keep data fresh.
    """
    from app.core.celery_app import celery_app

    for entry in celery_app.conf.beat_schedule.values():
        if entry.get("task") == "app.workers.market_data.sync_market_data":
            schedule = entry.get("schedule")
            if isinstance(schedule, (int, float)):
                return float(schedule) / 60.0
    return 10.0


@dataclass(frozen=True)
class CoverageRow:
    """What is stored for one symbol/timeframe pair."""

    symbol: str
    timeframe: str
    candle_count: int
    oldest: datetime | None
    newest: datetime | None
    is_stale: bool

    @property
    def has_data(self) -> bool:
        """Whether anything is stored at all."""
        return self.candle_count > 0

    def as_dict(self) -> dict[str, Any]:
        """Serialize for the API."""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "candle_count": self.candle_count,
            "oldest": self.oldest.isoformat() if self.oldest else None,
            "newest": self.newest.isoformat() if self.newest else None,
            "has_data": self.has_data,
            "is_stale": self.is_stale,
        }


class MarketCoverageService:
    """Reports and repairs market data coverage."""

    def __init__(self, session: AsyncSession, client: BinanceClient | None = None) -> None:
        self._session = session
        self._client = client or get_binance_client()
        self._settings = get_settings()
        self._sync_interval_minutes = _scheduled_sync_interval_minutes()

    @staticmethod
    def lookback_days(timeframe: str) -> int:
        """Days of history to keep for a timeframe."""
        return TIMEFRAME_LOOKBACK_DAYS.get(timeframe, DEFAULT_LOOKBACK_DAYS)

    async def get_coverage(
        self,
        symbols: list[str] | None = None,
        timeframes: list[str] | None = None,
    ) -> list[CoverageRow]:
        """Report stored candles for every configured symbol/timeframe pair.

        Missing pairs are returned with a zero count rather than omitted, so a
        caller can distinguish "nothing stored" from "not covered".
        """
        symbols = symbols or self._settings.market_symbol_list
        timeframes = timeframes or self._settings.market_timeframe_list

        rows = (
            await self._session.execute(
                select(
                    Candle.symbol,
                    Candle.timeframe,
                    func.count().label("n"),
                    func.min(Candle.timestamp).label("oldest"),
                    func.max(Candle.timestamp).label("newest"),
                )
                .where(Candle.symbol.in_(symbols), Candle.timeframe.in_(timeframes))
                .group_by(Candle.symbol, Candle.timeframe)
            )
        ).all()
        stored = {(r.symbol, r.timeframe): r for r in rows}

        now = datetime.now(UTC)
        coverage: list[CoverageRow] = []
        for symbol in symbols:
            for timeframe in timeframes:
                row = stored.get((symbol, timeframe))
                if row is None:
                    coverage.append(
                        CoverageRow(symbol, timeframe, 0, None, None, is_stale=True)
                    )
                    continue

                bar_minutes = TIMEFRAME_MINUTES.get(timeframe, 60)
                threshold = timedelta(
                    minutes=max(
                        bar_minutes * STALE_BAR_MULTIPLE,
                        self._sync_interval_minutes * SYNC_INTERVAL_GRACE,
                    )
                )
                age = now - row.newest
                coverage.append(
                    CoverageRow(
                        symbol=symbol,
                        timeframe=timeframe,
                        candle_count=int(row.n),
                        oldest=row.oldest,
                        newest=row.newest,
                        is_stale=age > threshold,
                    )
                )
        return coverage

    async def sync(
        self,
        symbols: list[str] | None = None,
        timeframes: list[str] | None = None,
        only_missing_or_stale: bool = True,
    ) -> dict[str, Any]:
        """Backfill every pair that is missing or has fallen behind.

        Args:
            only_missing_or_stale: When False, refetch everything regardless of
                what is already stored.

        Returns:
            A per-pair report of how many candles were ingested.
        """
        coverage = await self.get_coverage(symbols, timeframes)
        targets = [
            row for row in coverage
            if not only_missing_or_stale or not row.has_data or row.is_stale
        ]

        downloader = HistoricalDownloaderService(self._session, client=self._client)
        results: list[dict[str, Any]] = []
        ingested = 0
        failed = 0

        for row in targets:
            # An incremental top-up only needs the recent tail; a cold start
            # needs the full lookback. A caller that explicitly asked for a
            # full sync wants the deep fetch even where data already exists --
            # otherwise `full=True` just re-checks every pair and still fetches
            # two days, which is not a resync at all.
            days = (
                TOP_UP_DAYS
                if only_missing_or_stale and row.has_data
                else self.lookback_days(row.timeframe)
            )
            try:
                count = await downloader.download_history(row.symbol, row.timeframe, days=days)
                ingested += count
                results.append(
                    {"symbol": row.symbol, "timeframe": row.timeframe,
                     "candles": count,
                     "mode": "top_up" if days == TOP_UP_DAYS else "backfill"}
                )
            except Exception as exc:
                # One bad pair must not abandon the other forty-seven.
                failed += 1
                logger.error(
                    "market_sync_failed",
                    symbol=row.symbol, timeframe=row.timeframe, error=str(exc),
                )
                results.append(
                    {"symbol": row.symbol, "timeframe": row.timeframe, "error": str(exc)[:200]}
                )
            await asyncio.sleep(0.05)

        logger.info(
            "market_data_synced",
            pairs_attempted=len(targets), candles_ingested=ingested, failed=failed,
        )
        return {
            "pairs_checked": len(coverage),
            "pairs_synced": len(targets),
            "pairs_failed": failed,
            "candles_ingested": ingested,
            "details": results,
        }

    async def summary(self) -> dict[str, Any]:
        """A one-glance view of coverage completeness."""
        coverage = await self.get_coverage()
        with_data = [c for c in coverage if c.has_data]
        return {
            "symbols": self._settings.market_symbol_list,
            "timeframes": self._settings.market_timeframe_list,
            "pairs_total": len(coverage),
            "pairs_with_data": len(with_data),
            "pairs_missing": len(coverage) - len(with_data),
            "pairs_stale": len([c for c in with_data if c.is_stale]),
            "total_candles": sum(c.candle_count for c in coverage),
            "coverage": [c.as_dict() for c in coverage],
        }
