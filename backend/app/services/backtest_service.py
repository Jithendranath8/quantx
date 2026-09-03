"""
QuantX — Backtest Service.

Queries candle data from PostgreSQL and executes the BacktestEngine.

The engine is pure CPU-bound pandas work. Calling it directly from an async
route blocks the event loop for the whole run, freezing every other request on
that worker, so it is dispatched to the threadpool.
"""

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.engines.backtest.engine import BacktestEngine
from app.models.market_data import Candle
from app.schemas.backtest import BacktestRequest, BacktestResult


class BacktestService:
    """Service orchestrating backtesting execution."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def run_backtest(self, req: BacktestRequest) -> BacktestResult:
        """Fetch candles for the request window and run the simulation."""
        settings = get_settings()

        if req.start_date and req.end_date and req.start_date >= req.end_date:
            raise ValidationError("start_date must be earlier than end_date")

        stmt = select(Candle).where(
            Candle.symbol == req.symbol.upper(),
            Candle.timeframe == req.timeframe,
        )
        # Honour the requested window instead of silently ignoring it and
        # always taking the oldest 1000 rows in the table.
        if req.start_date:
            stmt = stmt.where(Candle.timestamp >= req.start_date)
        if req.end_date:
            stmt = stmt.where(Candle.timestamp <= req.end_date)

        stmt = stmt.order_by(Candle.timestamp.asc()).limit(settings.backtest_max_candles)

        candles = list((await self._session.execute(stmt)).scalars().all())

        df = pd.DataFrame(
            [
                {
                    "timestamp": c.timestamp,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                }
                for c in candles
            ]
        )

        engine = BacktestEngine(req)
        return await run_in_threadpool(engine.run, df)

    def run_backtest_sync(self, df: pd.DataFrame, req: BacktestRequest) -> BacktestResult:
        """Run the engine directly on a provided frame (used by research tools)."""
        return BacktestEngine(req).run(df)

    async def load_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """Load candles as a chronological DataFrame for research engines."""
        settings = get_settings()
        stmt = (
            select(Candle)
            .where(Candle.symbol == symbol.upper(), Candle.timeframe == timeframe)
            .order_by(Candle.timestamp.asc())
            .limit(min(limit or settings.backtest_max_candles, settings.backtest_max_candles))
        )
        candles = list((await self._session.execute(stmt)).scalars().all())
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
                for c in candles
            ]
        )
