"""
QuantX — Agent Tools: risk engine.

The risk engine is the hard gate every proposed trade must clear. These tools
let an agent *ask* whether a trade is permitted and read the persisted risk
state, but the engine stays deterministic and non-overridable: an agent can
query it, never relax it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.tools.base import Tool, ToolContext, ToolResult
from app.engines.risk.manager import RiskManager
from app.schemas.risk import TradeRiskRequest
from app.services.risk_state_service import RiskStateService


class _ValidateTradeArgs(BaseModel):
    symbol: str = Field(..., min_length=3, max_length=20)
    action: str = Field(..., description="BUY or SELL")
    order_amount_usd: float = Field(..., gt=0.0)
    entry_price: float = Field(..., gt=0.0)
    stop_loss_price: float | None = Field(default=None, description="Stop-loss price, if any")
    leverage: int = Field(default=1, ge=1)
    active_positions_count: int = Field(default=0, ge=0)
    current_exposure_usd: float = Field(default=0.0, ge=0.0)


class ValidateTradeTool(Tool[_ValidateTradeArgs]):
    name = "validate_trade"
    description = (
        "Check a proposed trade against the deterministic risk engine (per-trade risk, "
        "daily loss, leverage, concurrency, exposure, circuit breaker) and return whether "
        "it is approved plus the recommended position size. This never approves anything "
        "the hard limits forbid."
    )
    args_model = _ValidateTradeArgs

    async def _run(self, args: _ValidateTradeArgs, ctx: ToolContext) -> ToolResult:
        state = RiskStateService(ctx.session)
        config = None
        current_daily_loss = 0.0
        if ctx.user_id is not None:
            config = await state.load_config(ctx.user_id)
            risk_state = await state.get_or_create(ctx.user_id)
            current_daily_loss = float(getattr(risk_state, "daily_loss_usd", 0.0) or 0.0)

        request = TradeRiskRequest(
            symbol=args.symbol.upper(),
            action=args.action.upper(),
            account_balance=ctx.account_balance,
            order_amount_usd=args.order_amount_usd,
            leverage=args.leverage,
            stop_loss_price=args.stop_loss_price,
            entry_price=args.entry_price,
            current_daily_loss_usd=current_daily_loss,
            active_positions_count=args.active_positions_count,
            current_exposure_usd=args.current_exposure_usd,
        )
        result = RiskManager(config).validate_trade(request)
        return self._ok(result.model_dump())


class _RiskStateArgs(BaseModel):
    pass


class GetRiskStateTool(Tool[_RiskStateArgs]):
    name = "get_risk_state"
    description = "Read the authenticated user's persisted risk state: halt status and daily loss."
    args_model = _RiskStateArgs

    async def _run(self, args: _RiskStateArgs, ctx: ToolContext) -> ToolResult:
        user_id = self._require_user(ctx)
        state = RiskStateService(ctx.session)
        halted = await state.is_halted(user_id)
        risk_state = await state.get_or_create(user_id)
        return self._ok(
            {
                "halted": halted,
                "daily_loss_usd": float(getattr(risk_state, "daily_loss_usd", 0.0) or 0.0),
                "circuit_breaker_active": bool(getattr(risk_state, "circuit_breaker_active", False)),
            }
        )
