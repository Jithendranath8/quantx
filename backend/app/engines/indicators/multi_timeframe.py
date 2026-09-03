"""
QuantX — Multi-Timeframe Indicator Engine.

Computes technical indicators across several timeframes and builds a unified
multi-timeframe market snapshot.

Timeframes are de-duplicated, validated against a whitelist and capped in
number, and the pandas maths for all of them runs once in the threadpool.
Previously an unvalidated caller-supplied list was processed inline, so a
single request could issue hundreds of queries and hundreds of full indicator
passes on the event loop.

Candle loads are issued sequentially on purpose: an AsyncSession is not safe
for concurrent use, so gathering queries against one session raises
"concurrent operations are not permitted". The cap keeps the count small, and
the indicator maths -- not the queries -- is what actually dominates here.
"""

from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.engines.indicators.registry import IndicatorRegistry
from app.models.market_data import Candle

SUPPORTED_TIMEFRAMES = (
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w",
)
DEFAULT_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h"]
MAX_CANDLES_PER_TIMEFRAME = 1000


class MultiTimeframeEngine:
    """Engine for multi-timeframe technical analysis."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._registry = IndicatorRegistry()

    @staticmethod
    def validate_timeframes(timeframes: list[str] | None) -> list[str]:
        """Normalize, de-duplicate, whitelist and cap a timeframe list.

        Raises:
            ValidationError: On an unknown timeframe or too many of them.
        """
        if not timeframes:
            return list(DEFAULT_TIMEFRAMES)

        seen: list[str] = []
        for raw in timeframes:
            tf = raw.strip()
            if tf not in SUPPORTED_TIMEFRAMES:
                raise ValidationError(
                    f"Unsupported timeframe '{tf}'",
                    {"supported": list(SUPPORTED_TIMEFRAMES)},
                )
            if tf not in seen:
                seen.append(tf)

        max_allowed = get_settings().max_timeframes_per_request
        if len(seen) > max_allowed:
            raise ValidationError(
                f"Too many timeframes requested ({len(seen)}); maximum is {max_allowed}",
                {"max_timeframes": max_allowed},
            )
        return seen

    async def get_multi_timeframe_indicators(
        self,
        symbol: str,
        timeframes: list[str] | None = None,
        limit: int = 200,
    ) -> dict[str, dict[str, Any]]:
        """Compute an indicator snapshot across timeframes.

        Args:
            symbol: Trading symbol (e.g. BTCUSDT).
            timeframes: Timeframes to process; defaults to a standard set.
            limit: Candles to load per timeframe.

        Returns:
            Mapping of timeframe -> indicator values.
        """
        validated = self.validate_timeframes(timeframes)
        limit = min(max(1, limit), MAX_CANDLES_PER_TIMEFRAME)
        symbol = symbol.upper()

        frames = [await self._load_frame(symbol, tf, limit) for tf in validated]

        def _compute_all() -> dict[str, dict[str, Any]]:
            return {
                tf: (self._registry.compute_indicator_summary(df) if not df.empty else {})
                for tf, df in zip(validated, frames, strict=True)
            }

        return await run_in_threadpool(_compute_all)

    async def _load_frame(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Load one timeframe's candles as a chronological DataFrame."""
        stmt = (
            select(Candle)
            .where(Candle.symbol == symbol, Candle.timeframe == timeframe)
            .order_by(Candle.timestamp.desc())
            .limit(limit)
        )
        candles = list((await self._session.execute(stmt)).scalars().all())
        if not candles:
            return pd.DataFrame()

        return pd.DataFrame(
            [
                {
                    "timestamp": c.timestamp,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                }
                for c in reversed(candles)
            ]
        )
