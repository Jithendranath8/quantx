"""
QuantX — Multi-agent orchestration API.

Exposes the LangGraph specialist pipeline over HTTP. Each call runs several
model turns, so it is authenticated and tightly rate limited.

Execution safety: the ``execute`` flag only ever enables *paper* orders, and a
paper order is placed solely when the risk engine and the deterministic
validator both allow the decision. Live trading is not reachable here.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.agents.llm import build_provider
from app.agents.orchestration import build_orchestrator
from app.agents.tools.base import ToolContext
from app.connectors.binance_client import get_binance_client
from app.core.config import get_settings
from app.core.dependencies import CurrentUser, DBSession, RateLimiter
from app.schemas.agent import OrchestrationResponse

router = APIRouter(prefix="/agent", tags=["AI Trading Agent"])


@router.post(
    "/orchestrate",
    response_model=OrchestrationResponse,
    summary="Run the multi-agent orchestration for a symbol",
    description=(
        "Runs the market, technical, quant and risk specialists under a LangGraph "
        "supervisor, synthesizes one deterministically-validated decision, and "
        "optionally places a paper order. Requires a configured LLM provider."
    ),
    dependencies=[Depends(RateLimiter("agent_orchestrate", max_requests=10))],
)
async def orchestrate_symbol(
    user: CurrentUser,
    db: DBSession,
    symbol: str = Query("BTCUSDT", min_length=3, max_length=20),
    execute: bool = Query(False, description="Allow a paper order if the decision is actionable"),
) -> OrchestrationResponse:
    """Run the agentic pipeline and return the decision plus specialist reports."""
    settings = get_settings()
    if not settings.agent_runtime_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No LLM provider configured. Set ANTHROPIC_API_KEY, or OPENAI_API_KEY / "
                "OPENAI_BASE_URL for an OpenAI-compatible (incl. local) endpoint."
            ),
        )

    ctx = ToolContext(
        session=db,
        user_id=user.id,
        client=get_binance_client(),
        allow_mutations=execute,
    )
    orchestrator = build_orchestrator(build_provider(), ctx)
    state = await orchestrator.run(symbol)

    return OrchestrationResponse(
        symbol=state.symbol,
        decision=state.final_decision,
        reports={key: report.summary for key, report in state.reports.items()},
        halted=state.halted,
        market_price=state.market_price,
        executed_order=state.executed_order,
        log=state.log,
    )
