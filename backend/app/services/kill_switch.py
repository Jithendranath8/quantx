"""
QuantX — Emergency Kill Switch Service.

When activated:
1. Engages the persisted circuit breaker (halts new decisions, strategies, AI)
2. Cancels the user's open orders on Binance, then VERIFIES they are gone
3. Cancels the user's pending paper orders
4. Records the incident in the immutable EventLedger
5. Alerts the operator
6. Reports exactly what succeeded and what did not

Failure to cancel on the exchange is reported as a failure. Silently swallowing
the error and returning a success payload is worse than not having a kill
switch at all, because the operator believes they are flat when they are not.
"""

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.binance_client import BinanceClient, get_binance_client
from app.core.logging import get_logger
from app.core.metrics import CIRCUIT_BREAKER_EVENTS_TOTAL
from app.models.live_trading import LiveOrder
from app.models.paper_trading import PaperAccount, PaperOrder
from app.services.event_ledger_service import EventLedgerService
from app.services.notification_service import NotificationService
from app.services.risk_state_service import RiskStateService

logger = get_logger(__name__)

# Binance statuses that mean the order is no longer working.
_TERMINAL_STATUSES = {"CANCELED", "FILLED", "EXPIRED", "REJECTED"}


class KillSwitchService:
    """Handles emergency trading halt and open-order cancellation."""

    def __init__(self, session: AsyncSession, client: BinanceClient | None = None) -> None:
        self._session = session
        self._client = client or get_binance_client()
        self._ledger = EventLedgerService(session)
        self._risk_state = RiskStateService(session)

    async def activate_kill_switch(
        self,
        user_id: uuid.UUID,
        reason: str = "EMERGENCY_USER_ACTIVATED",
    ) -> dict[str, Any]:
        """Activate the emergency kill switch for one user.

        Returns:
            A report describing what was halted and cancelled. ``fully_successful``
            is False whenever any exchange cancellation could not be confirmed.
        """
        logger.critical("EMERGENCY_KILL_SWITCH_ACTIVATED", user_id=str(user_id), reason=reason)
        CIRCUIT_BREAKER_EVENTS_TOTAL.inc()

        errors: list[str] = []

        # 1. Halt first, durably. Even if cancellation fails, no NEW orders
        #    can be placed while we work through the rest.
        await self._risk_state.set_circuit_breaker(user_id, True, reason)
        await self._session.commit()

        # 2. Cancel this user's open orders on the exchange, then verify.
        binance_cancelled, binance_failed, binance_errors = await self._cancel_exchange_orders(user_id)
        errors.extend(binance_errors)

        # 3. Cancel this user's pending paper orders (scoped to their accounts).
        paper_cancelled = await self._cancel_paper_orders(user_id)

        total_cancelled = binance_cancelled + paper_cancelled
        fully_successful = not errors and binance_failed == 0

        # 4. Immutable incident record.
        await self._ledger.log_event(
            source="KILL_SWITCH_SERVICE",
            event_type="EMERGENCY_KILL_SWITCH_ACTIVATED",
            payload={
                "reason": reason,
                "cancelled_paper_orders": paper_cancelled,
                "cancelled_binance_orders": binance_cancelled,
                "failed_binance_cancellations": binance_failed,
                "errors": errors,
                "fully_successful": fully_successful,
            },
            user_id=user_id,
            commit=False,
        )
        await self._session.commit()

        # 5. Alert.
        await NotificationService.send_alert(
            title="CRITICAL: Emergency Kill Switch Activated",
            message=(
                f"Trading halted. Reason: {reason}. "
                f"{total_cancelled} orders cancelled "
                f"({binance_cancelled} exchange, {paper_cancelled} paper)."
                + (f" {binance_failed} EXCHANGE CANCELLATIONS FAILED — VERIFY MANUALLY." if binance_failed else "")
            ),
            level="CRITICAL",
        )

        return {
            "status": "HALTED",
            "circuit_breaker_active": True,
            "reason": reason,
            "fully_successful": fully_successful,
            "total_orders_cancelled": total_cancelled,
            "paper_orders_cancelled": paper_cancelled,
            "binance_orders_cancelled": binance_cancelled,
            "binance_cancellations_failed": binance_failed,
            "errors": errors,
            "message": (
                f"Kill switch engaged. {total_cancelled} open orders cancelled."
                if fully_successful
                else "Kill switch engaged and trading halted, but one or more exchange "
                     "cancellations could NOT be confirmed. Verify your positions on Binance."
            ),
        }

    async def deactivate_kill_switch(self, user_id: uuid.UUID, reason: str = "MANUAL_RESET") -> dict[str, Any]:
        """Release the circuit breaker and allow trading to resume."""
        await self._risk_state.set_circuit_breaker(user_id, False, None)
        await self._ledger.log_event(
            source="KILL_SWITCH_SERVICE",
            event_type="KILL_SWITCH_DEACTIVATED",
            payload={"reason": reason},
            user_id=user_id,
            commit=False,
        )
        await self._session.commit()
        logger.warning("kill_switch_deactivated", user_id=str(user_id), reason=reason)
        return {"status": "ACTIVE", "circuit_breaker_active": False, "reason": reason}

    async def get_status(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Report the current halt state for a user."""
        state = await self._risk_state.get_or_create(user_id)
        return {
            "circuit_breaker_active": state.circuit_breaker_active,
            "reason": state.circuit_breaker_reason,
            "daily_loss_usd": state.daily_loss_usd,
            "current_drawdown_pct": state.current_drawdown_pct,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        }

    # ── Internals ────────────────────────────────────────────────────

    async def _cancel_exchange_orders(self, user_id: uuid.UUID) -> tuple[int, int, list[str]]:
        """Cancel and verify this user's own open Binance orders.

        Every user shares the operator's exchange account, so the account's
        open-order list contains other users' orders and orders placed outside
        QuantX. An exchange order is cancelled only when its client order id or
        exchange id matches one of the caller's own non-terminal rows. Selecting
        by symbol alone let one user's kill switch cancel everyone's orders.

        Returns:
            (cancelled_count, failed_count, error_messages)
        """
        cancelled = 0
        failed = 0
        errors: list[str] = []

        stmt = select(LiveOrder).where(
            LiveOrder.user_id == user_id,
            LiveOrder.is_testnet == self._client.testnet,
            LiveOrder.status.notin_(list(_TERMINAL_STATUSES)),
        )
        own_orders = list((await self._session.execute(stmt)).scalars().all())
        if not own_orders:
            return 0, 0, []

        own_by_client_id = {o.client_order_id: o for o in own_orders}
        own_by_exchange_id = {o.exchange_order_id: o for o in own_orders if o.exchange_order_id}

        for symbol in sorted({o.symbol for o in own_orders}):
            try:
                open_orders = await self._client.get_open_orders(symbol=symbol)
            except Exception as exc:
                failed += 1
                errors.append(f"Could not list open orders for {symbol}: {exc}")
                logger.error("kill_switch_list_orders_failed", symbol=symbol, error=str(exc))
                continue

            for order in open_orders:
                exchange_id = order.get("orderId")
                if exchange_id is None:
                    continue
                local = own_by_client_id.get(str(order.get("clientOrderId") or "")) or own_by_exchange_id.get(
                    str(exchange_id)
                )
                if local is None:
                    # Someone else's order on the shared account: not ours to cancel.
                    continue
                try:
                    await self._client.cancel_order(symbol=symbol, order_id=exchange_id)
                    confirmed = await self._verify_cancelled(symbol, exchange_id)
                    if confirmed:
                        cancelled += 1
                        local.exchange_order_id = str(exchange_id)
                        local.status = "CANCELED"
                    else:
                        failed += 1
                        errors.append(f"Order {exchange_id} on {symbol} did not reach a terminal state")
                except Exception as exc:
                    failed += 1
                    errors.append(f"Failed to cancel {exchange_id} on {symbol}: {exc}")
                    logger.error(
                        "kill_switch_cancel_failed",
                        symbol=symbol,
                        order_id=exchange_id,
                        error=str(exc),
                    )

        return cancelled, failed, errors

    async def _verify_cancelled(self, symbol: str, exchange_order_id: Any) -> bool:
        """Re-read the order from Binance to confirm it is genuinely gone."""
        try:
            order = await self._client.get_order(symbol, exchange_order_id)
            return order.get("status") in _TERMINAL_STATUSES
        except Exception as exc:
            logger.warning(
                "kill_switch_verify_failed",
                symbol=symbol,
                order_id=exchange_order_id,
                error=str(exc),
            )
            return False

    async def _cancel_paper_orders(self, user_id: uuid.UUID) -> int:
        """Cancel pending paper orders belonging to this user only."""
        account_ids = select(PaperAccount.id).where(PaperAccount.user_id == user_id)
        result = await self._session.execute(
            update(PaperOrder)
            .where(
                PaperOrder.account_id.in_(account_ids),
                PaperOrder.status == "PENDING",
            )
            .values(status="CANCELLED_BY_KILL_SWITCH")
        )
        return result.rowcount or 0  # type: ignore[attr-defined]  # DML execute returns CursorResult (has rowcount)
