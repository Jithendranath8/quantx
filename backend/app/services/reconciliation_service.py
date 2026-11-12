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
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.binance_client import BinanceClient, get_binance_client
from app.core.exceptions import BinanceRejectedError
from app.core.logging import get_logger
from app.models.live_trading import LiveOrder
from app.services.live_order_state import apply_exchange_result

logger = get_logger(__name__)

_OPEN_STATUSES = {"NEW", "PARTIALLY_FILLED", "PENDING_SUBMIT", "UNKNOWN_NEEDS_RECONCILIATION"}
# Statuses of a submit whose outcome was never learned.
_UNCONFIRMED_STATUSES = {"PENDING_SUBMIT", "UNKNOWN_NEEDS_RECONCILIATION"}
# Binance's code for "no such order".
_UNKNOWN_ORDER_CODE = -2013
# How long an unconfirmed submit is given to appear on the exchange before
# "the exchange has no such order" is taken to mean it never arrived.
_SUBMIT_GRACE = timedelta(minutes=2)


class OrderReconciliationService:
    """Cross-checks local platform state against Binance exchange state."""

    def __init__(self, session: AsyncSession, client: BinanceClient | None = None) -> None:
        self._session = session
        self._client = client or get_binance_client()

    async def reconcile_orders(self, user_id: uuid.UUID | None = None) -> dict[str, Any]:
        """Reconcile local live orders against the exchange.

        Covers every order that may still be working, plus orders that recorded
        a filled quantity without a fill price: the risk book cannot count
        those, so they are looked up again until the price is known.

        Args:
            user_id: Restrict to one user, or None to sweep every open order.

        Returns:
            A report listing each discrepancy found and any repairs applied.
        """
        mismatches: list[dict[str, Any]] = []
        repaired = 0

        stmt = select(LiveOrder).where(
            # The other venue's orders cannot be looked up with this client.
            LiveOrder.is_testnet == self._client.testnet,
            or_(
                LiveOrder.status.in_(list(_OPEN_STATUSES)),
                and_(LiveOrder.filled_quantity > 0, LiveOrder.filled_price.is_(None)),
            ),
        )
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
                apply_exchange_result(local, remote)
                repaired += 1
            elif not local.exchange_order_id and remote.get("orderId"):
                local.exchange_order_id = str(remote["orderId"])
                repaired += 1

        if repaired:
            await self._session.commit()

        return self._report(mismatches, repaired, checked=len(local_orders), unreachable=unreachable)

    async def _resolve_missing(self, local: LiveOrder) -> bool:
        """Look a locally-open order up directly; adopt the exchange's answer.

        The lookup uses the exchange id when one was recorded and otherwise the
        client order id, which is the only handle on a submit whose response
        was lost. Returning False without looking, as this did whenever the
        exchange id was missing, left exactly those orders unresolved forever.
        """
        try:
            if local.exchange_order_id:
                remote = await self._client.get_order(local.symbol, local.exchange_order_id)
            else:
                remote = await self._client.get_order(local.symbol, client_order_id=local.client_order_id)
        except BinanceRejectedError as exc:
            details = exc.details if isinstance(exc.details, dict) else {}
            if details.get("code") == _UNKNOWN_ORDER_CODE and self._never_arrived(local):
                local.status = "REJECTED"
                local.rejection_reason = "Submit never reached the exchange (no order with this client id)"
                return True
            logger.warning(
                "reconciliation_lookup_rejected",
                client_order_id=local.client_order_id,
                error=str(exc),
            )
            return False
        except Exception as exc:
            logger.warning(
                "reconciliation_lookup_failed",
                client_order_id=local.client_order_id,
                error=str(exc),
            )
            return False

        apply_exchange_result(local, remote)
        return True

    @staticmethod
    def _never_arrived(local: LiveOrder) -> bool:
        """An unconfirmed submit, old enough that the exchange would know it."""
        if local.status not in _UNCONFIRMED_STATUSES or local.exchange_order_id:
            return False
        created = local.created_at
        if created is None:
            return False
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return datetime.now(UTC) - created > _SUBMIT_GRACE

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
