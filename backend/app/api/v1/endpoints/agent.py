"""
QuantX — AI Trading Agent API Endpoints.

Each call costs an OpenAI request, so this is authenticated and tightly rate
limited.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.endpoints.orchestrator import agent_runs
from app.core.config import get_settings
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
    symbol: str = Query("BTCUSDT", pattern=r"^[A-Za-z0-9]{3,20}$"),
) -> AgentDecision:
    """Evaluate the market context for a symbol using the AI agent."""
    user_id = user.id
    async with agent_runs.slot(str(user_id)):
        try:
            async with asyncio.timeout(get_settings().agent_run_timeout_seconds):
                return await AgentService(db).evaluate_symbol(symbol=symbol.upper(), user_id=user_id)
        except TimeoutError as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="The agent run exceeded its time limit and was stopped.",
            ) from exc
