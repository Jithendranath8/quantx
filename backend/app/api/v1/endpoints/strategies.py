"""
QuantX — Strategy API Endpoints.

List registered strategies and evaluate one against stored market data.
"""

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import CurrentUser, DBSession, RateLimiter
from app.engines.strategy.base import Signal
from app.services.strategy_service import StrategyService

router = APIRouter(prefix="/strategies", tags=["Strategy Engine"])


@router.get(
    "",
    summary="List available strategies",
)
async def list_strategies(user: CurrentUser, db: DBSession) -> list[dict[str, str]]:
    """List every registered strategy with its description."""
    return StrategyService(db).list_available_strategies()


@router.get(
    "/evaluate",
    response_model=Signal,
    summary="Evaluate a strategy against stored candles",
    dependencies=[Depends(RateLimiter("strategy_evaluate", max_requests=60))],
)
async def evaluate_strategy(
    user: CurrentUser,
    db: DBSession,
    strategy_name: str = Query("ema_crossover"),
    symbol: str = Query("BTCUSDT"),
    timeframe: str = Query("1h"),
    limit: int = Query(200, ge=20, le=1000),
) -> Signal:
    """Run one strategy over recent candles and return its signal."""
    return await StrategyService(db).evaluate_strategy(
        strategy_name=strategy_name,
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
    )
