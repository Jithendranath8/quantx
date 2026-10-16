"""
QuantX — Market-Making API Endpoints.

Runs the Avellaneda-Stoikov market-making simulation over stored candles and
returns its performance, the quote/inventory/P&L series, and the fills. Pure
research/simulation: it never places an order anywhere.
"""

from fastapi import APIRouter, Depends

from app.core.dependencies import CurrentUser, DBSession, RateLimiter
from app.schemas.market_making import MarketMakingRequest, MarketMakingResult
from app.services.market_making_service import MarketMakingService

router = APIRouter(prefix="/market-making", tags=["Market Making"])


@router.post(
    "/simulate",
    response_model=MarketMakingResult,
    summary="Run an Avellaneda-Stoikov market-making simulation",
    dependencies=[Depends(RateLimiter("market_making_simulate", max_requests=10))],
)
async def simulate_market_making(
    req: MarketMakingRequest,
    user: CurrentUser,
    db: DBSession,
) -> MarketMakingResult:
    """Simulate inventory-aware market making and return full analytics."""
    return await MarketMakingService(db).simulate(req)
