"""
QuantX — Market-Making Service.

Loads candle history from PostgreSQL and runs the Avellaneda-Stoikov simulation.
Like the backtest engine it is pure CPU-bound pandas/numpy work, so it is
dispatched to the threadpool rather than blocking the event loop.
"""

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.engines.market_making.engine import MarketMakingEngine
from app.models.market_data import Candle
from app.schemas.market_making import MarketMakingRequest, MarketMakingResult


class MarketMakingService:
    """Service orchestrating market-making simulations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def simulate(self, req: MarketMakingRequest) -> MarketMakingResult:
        """Fetch candles for the request window and run the simulation."""
        if req.start_date and req.end_date and req.start_date >= req.end_date:
            raise ValidationError("start_date must be earlier than end_date")

        settings = get_settings()
        stmt = select(Candle).where(
            Candle.symbol == req.symbol.upper(),
            Candle.timeframe == req.timeframe,
        )
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

        engine = MarketMakingEngine(req)
        return await run_in_threadpool(engine.run, df)
