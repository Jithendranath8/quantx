"""
QuantX — AI Trading Agent API Endpoints.

Each call costs an OpenAI request, so this is authenticated and tightly rate
limited.
"""

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import CurrentUser, DBSession, RateLimiter
from app.schemas.agent import AgentDecision
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agent", tags=["AI Trading Agent"])


@router.get(
    "/analyze",
    response_model=AgentDecision,
    summary="Get an AI Trading Agent decision for a symbol",
    description=(
        "Assembles market context from stored data (OHLCV, indicators, MTF trend, "
        "funding, OI, your open positions), invokes the model, and validates the "
        "result deterministically. A decision failing validation is returned as WAIT."
    ),
    dependencies=[Depends(RateLimiter("agent_analyze", max_requests=20))],
)
async def analyze_symbol(
    user: CurrentUser,
    db: DBSession,
    symbol: str = Query("BTCUSDT", min_length=3, max_length=20),
) -> AgentDecision:
    """Evaluate the market context for a symbol using the AI agent."""
    return await AgentService(db).evaluate_symbol(symbol=symbol, user_id=user.id)
