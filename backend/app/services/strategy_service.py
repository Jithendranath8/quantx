"""
QuantX — Strategy Service.

Executes quantitative strategies against historical/live market data
and generates trade signals.
"""

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.engines.indicators.registry import IndicatorRegistry
from app.engines.strategy.base import Signal
from app.engines.strategy.registry import StrategyRegistry
from app.models.market_data import Candle


class StrategyService:
    """Service for evaluating trading strategies."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._strategy_registry = StrategyRegistry()
        self._indicator_registry = IndicatorRegistry()

    def list_available_strategies(self) -> list[dict[str, str]]:
        """List registered strategies."""
        return self._strategy_registry.list_strategies()

    async def evaluate_strategy(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 200,
    ) -> Signal:
        """Evaluate strategy against market candles and return signal."""
        strategy = self._strategy_registry.get(strategy_name)
        if not strategy:
            return Signal(
                action="WAIT",
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                reasoning=f"Strategy '{strategy_name}' not found",
            )

        # Query candle data
        stmt = (
            select(Candle)
            .where(Candle.symbol == symbol.upper(), Candle.timeframe == timeframe)
            .order_by(Candle.timestamp.desc())
            .limit(min(max(20, limit), 1000))
        )
        result = await self._session.execute(stmt)
        candles = list(result.scalars().all())

        if not candles or len(candles) < 20:
            return Signal(
                action="WAIT",
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                reasoning="Insufficient candles in database to evaluate strategy",
            )

        # Convert to DataFrame in chronological order
        data = [
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
        df = pd.DataFrame(data)

        # Indicator maths is synchronous pandas work. Running it inline would
        # block the event loop for every other request on this worker, so it is
        # offloaded to the threadpool.
        def _evaluate() -> Signal:
            df_computed = self._indicator_registry.compute_all(df)
            return strategy.generate_signal(symbol=symbol, timeframe=timeframe, df=df_computed)

        return await run_in_threadpool(_evaluate)
