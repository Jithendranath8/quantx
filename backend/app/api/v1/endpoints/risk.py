"""
QuantX — Risk Engine API Endpoints.

Query risk configuration and evaluate proposed trades against hard rules.

The circuit-breaker control is authenticated and writes to persistent
per-user state. It was previously unauthenticated and mutated a module-level
object, so anyone could re-enable trading and only in one worker process.
"""

from typing import Any

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser, DBSession
from app.engines.risk.manager import RiskManager
from app.schemas.risk import RiskCheckResult, RiskConfig, TradeRiskRequest
from app.services.risk_state_service import RiskStateService

router = APIRouter(prefix="/risk", tags=["Risk Engine"])


@router.get(
    "/config",
    response_model=RiskConfig,
    summary="Get active risk parameters",
)
async def get_risk_config(user: CurrentUser, db: DBSession) -> RiskConfig:
    """Return the risk configuration in force for this user."""
    return await RiskStateService(db).load_config(user.id)


@router.post(
    "/validate",
    response_model=RiskCheckResult,
    summary="Validate a proposed trade against hard risk rules",
)
async def validate_trade_risk(
    request: TradeRiskRequest,
    user: CurrentUser,
    db: DBSession,
) -> RiskCheckResult:
    """Evaluate a proposed trade, honouring the persisted circuit breaker.

    A validation that trips the breaker persists it, so the halt applies to
    every subsequent request in every worker.
    """
    service = RiskStateService(db)
    config = await service.load_config(user.id)
    result = RiskManager(config).validate_trade(request)

    if result.circuit_breaker_triggered and not config.circuit_breaker_active:
        await service.set_circuit_breaker(user.id, True, result.rejection_reason)
        await db.commit()

    return result


@router.post(
    "/circuit-breaker/toggle",
    summary="Manually engage or release the circuit breaker",
)
async def toggle_circuit_breaker(
    user: CurrentUser,
    db: DBSession,
    active: bool = Query(..., description="True to halt trading, false to resume"),
    reason: str = Query("MANUAL_TOGGLE", max_length=255),
) -> dict[str, Any]:
    """Set the persisted circuit breaker state for this user."""
    service = RiskStateService(db)
    state = await service.set_circuit_breaker(user.id, active, reason if active else None)
    await db.commit()
    return {
        "message": f"Circuit breaker state set to {active}",
        "circuit_breaker_active": state.circuit_breaker_active,
        "reason": state.circuit_breaker_reason,
    }


@router.get(
    "/state",
    summary="Persisted risk state",
)
async def get_risk_state(user: CurrentUser, db: DBSession) -> dict[str, Any]:
    """Return the durable risk counters for this user."""
    state = await RiskStateService(db).get_or_create(user.id)
    return {
        "circuit_breaker_active": state.circuit_breaker_active,
        "circuit_breaker_reason": state.circuit_breaker_reason,
        "daily_loss_usd": state.daily_loss_usd,
        "peak_portfolio_value": state.peak_portfolio_value,
        "current_drawdown_pct": state.current_drawdown_pct,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }
