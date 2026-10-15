"""
QuantX — Agent Tools: paper trading & safety.

Deliberate safety boundary: an agent can read positions, place **paper** orders,
and trip the kill switch — but it has **no tool that places a live order**. Live
execution stays behind the explicit mainnet interlock and the API, never behind
a model's tool call. The agent proposes and simulates; a human promotes.

The order tool is ``mutating`` and therefore refused unless the context was
constructed with ``allow_mutations=True``.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.agents.tools.base import Tool, ToolContext, ToolResult
from app.schemas.paper_trading import PaperPositionSchema, SubmitPaperOrderRequest
from app.services.kill_switch import KillSwitchService
from app.services.paper_trading_service import PaperTradingService


class _PositionsArgs(BaseModel):
    account_id: str | None = Field(
        default=None, description="Paper account UUID; defaults to the user's first account."
    )


class GetPositionsTool(Tool[_PositionsArgs]):
    name = "get_positions"
    description = "List the authenticated user's open paper-trading positions."
    args_model = _PositionsArgs

    async def _run(self, args: _PositionsArgs, ctx: ToolContext) -> ToolResult:
        user_id = self._require_user(ctx)
        service = PaperTradingService(ctx.session, ctx.client)
        account_id = await _resolve_account_id(service, ctx, args.account_id)
        if account_id is None:
            return self._err("No paper account found for this user. Create one first.")
        positions = await service.get_positions(user_id, account_id)
        return self._ok(
            {
                "account_id": str(account_id),
                "positions": [PaperPositionSchema.model_validate(p).model_dump(mode="json") for p in positions],
            }
        )


class _SubmitOrderArgs(BaseModel):
    symbol: str = Field(..., min_length=3, max_length=20)
    side: Literal["BUY", "SELL"] = Field(..., description="BUY or SELL")
    quantity: float = Field(..., gt=0.0)
    account_id: str | None = Field(default=None, description="Paper account UUID; defaults to first account.")
    stop_loss: float | None = None
    take_profit: float | None = None

    @field_validator("side", mode="before")
    @classmethod
    def _normalize_side(cls, value: object) -> object:
        """Accept any case; the fill engine only understands BUY/SELL."""
        return value.upper() if isinstance(value, str) else value


class SubmitPaperOrderTool(Tool[_SubmitOrderArgs]):
    name = "submit_paper_order"
    description = (
        "Submit a MARKET paper-trading order (simulated fill, slippage and fees applied). "
        "Paper only — this never touches a real exchange. Requires mutations to be enabled."
    )
    args_model = _SubmitOrderArgs
    mutating = True

    async def _run(self, args: _SubmitOrderArgs, ctx: ToolContext) -> ToolResult:
        user_id = self._require_user(ctx)
        service = PaperTradingService(ctx.session, ctx.client)
        account_id = await _resolve_account_id(service, ctx, args.account_id)
        if account_id is None:
            return self._err("No paper account found for this user. Create one first.")

        req = SubmitPaperOrderRequest(
            account_id=account_id,
            symbol=args.symbol.upper(),
            side=args.side,
            order_type="MARKET",
            quantity=args.quantity,
            stop_loss=args.stop_loss,
            take_profit=args.take_profit,
        )
        order = await service.submit_order(user_id, req)
        return self._ok(
            {
                "order_id": str(order.id),
                "symbol": order.symbol,
                "side": order.side,
                "quantity": order.quantity,
                "filled_price": order.filled_price,
                "status": order.status,
            }
        )


class _KillSwitchArgs(BaseModel):
    reason: str = Field(default="AGENT_TRIGGERED", max_length=255)


class ActivateKillSwitchTool(Tool[_KillSwitchArgs]):
    name = "activate_kill_switch"
    description = (
        "Emergency halt: stop trading, cancel all open orders, and engage the circuit breaker "
        "for the authenticated user. Use only when risk conditions demand an immediate stop."
    )
    args_model = _KillSwitchArgs
    mutating = True

    async def _run(self, args: _KillSwitchArgs, ctx: ToolContext) -> ToolResult:
        user_id = self._require_user(ctx)
        service = KillSwitchService(ctx.session, ctx.client)
        result = await service.activate_kill_switch(user_id=user_id, reason=args.reason)
        return self._ok(result if isinstance(result, dict) else {"activated": True})


async def _resolve_account_id(
    service: PaperTradingService, ctx: ToolContext, account_id: str | None
) -> uuid.UUID | None:
    """Return a UUID account id, defaulting to the user's first account when unspecified."""
    user_id = ctx.user_id
    if user_id is None:
        raise PermissionError("This tool requires an authenticated user in context.")
    if account_id:
        return uuid.UUID(account_id)
    accounts = await service.list_accounts(user_id)
    return accounts[0].id if accounts else None
