"""
QuantX — Order Reconciliation Service.

Compares local order state against Binance to detect:
- Local order believed open but absent on the exchange
- Exchange order with no local record (placed outside QuantX)
- Status / filled-quantity mismatches

Orders left in ``UNKNOWN_NEEDS_RECONCILIATION`` by an indeterminate submit are
resolved here by looking them up via their client_order_id.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.binance_client import BinanceClient, get_binance_client
from app.core.logging import get_logger
from app.models.live_trading import LiveOrder

logger = get_logger(__name__)

_OPEN_STATUSES = {"NEW", "PARTIALLY_FILLED", "PENDING_SUBMIT", "UNKNOWN_NEEDS_RECONCILIATION"}


class OrderReconciliationService:
    """Cross-checks local platform state against Binance exchange state."""

    def __init__(self, session: AsyncSession, client: BinanceClient | None = None) -> None:
        self._session = session
        self._client = client or get_binance_client()

    async def reconcile_orders(self, user_id: uuid.UUID | None = None) -> dict[str, Any]:
        """Reconcile local live orders against the exchange.

        Args:
            user_id: Restrict to one user, or None to sweep every open order.

        Returns:
            A report listing each discrepancy found and any repairs applied.
        """
        mismatches: list[dict[str, Any]] = []
        repaired = 0

        stmt = select(LiveOrder).where(LiveOrder.status.in_(list(_OPEN_STATUSES)))
        if user_id is not None:
            stmt = stmt.where(LiveOrder.user_id == user_id)
        local_orders = list((await self._session.execute(stmt)).scalars().all())

        if not local_orders:
            return self._report([], 0, checked=0)

        symbols = sorted({o.symbol for o in local_orders})
        exchange_by_client_id: dict[str, dict[str, Any]] = {}
        unreachable: list[str] = []

        for symbol in symbols:
            try:
                for order in await self._client.get_open_orders(symbol=symbol):
                    key = order.get("clientOrderId")
                    if key:
                        exchange_by_client_id[key] = order
            except Exception as exc:
                unreachable.append(symbol)
                logger.warning("reconciliation_query_failed", symbol=symbol, error=str(exc))

        for local in local_orders:
            if local.symbol in unreachable:
                # Cannot form a conclusion without exchange data; do not
                # "repair" the record on the basis of a failed query.
                continue

            remote = exchange_by_client_id.get(local.client_order_id)
            if remote is None:
                resolved = await self._resolve_missing(local)
                if resolved:
                    repaired += 1
                    continue
                mismatches.append(
                    {
                        "type": "LOCAL_ORDER_MISSING_ON_EXCHANGE",
                        "local_order_id": str(local.id),
                        "client_order_id": local.client_order_id,
                        "symbol": local.symbol,
                        "local_status": local.status,
                        "message": (
                            f"Order {local.client_order_id} is {local.status} locally "
                            f"but is not open on Binance and could not be looked up"
                        ),
                    }
                )
                continue

            remote_status = remote.get("status", "")
            remote_filled = float(remote.get("executedQty", 0) or 0)
            if remote_status != local.status or abs(remote_filled - local.filled_quantity) > 1e-12:
                mismatches.append(
                    {
                        "type": "STATUS_MISMATCH",
                        "local_order_id": str(local.id),
                        "symbol": local.symbol,
                        "local_status": local.status,
                        "exchange_status": remote_status,
                        "local_filled": local.filled_quantity,
                        "exchange_filled": remote_filled,
                    }
                )
                local.status = remote_status or local.status
                local.filled_quantity = remote_filled
                local.exchange_order_id = str(remote.get("orderId") or local.exchange_order_id or "")
                repaired += 1

        if repaired:
            await self._session.commit()

        return self._report(mismatches, repaired, checked=len(local_orders), unreachable=unreachable)

    async def _resolve_missing(self, local: LiveOrder) -> bool:
        """Look a locally-open order up directly; adopt the exchange's answer."""
        if not local.exchange_order_id:
            return False
        try:
            remote = await self._client.get_order(local.symbol, local.exchange_order_id)
        except Exception as exc:
            logger.warning(
                "reconciliation_lookup_failed",
                client_order_id=local.client_order_id,
                error=str(exc),
            )
            return False

        local.status = remote.get("status", local.status)
        local.filled_quantity = float(remote.get("executedQty", 0) or 0)
        return True

    @staticmethod
    def _report(
        mismatches: list[dict[str, Any]],
        repaired: int,
        checked: int,
        unreachable: list[str] | None = None,
    ) -> dict[str, Any]:
        """Assemble the reconciliation report with a real timestamp."""
        return {
            "status": "RECONCILED" if not mismatches else "DISCREPANCY_DETECTED",
            "orders_checked": checked,
            "discrepancies_count": len(mismatches),
            "repaired_count": repaired,
            "unreachable_symbols": unreachable or [],
            "mismatches": mismatches,
            "last_reconciliation_timestamp": datetime.now(UTC).isoformat(),
        }
