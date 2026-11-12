"""
QuantX — Applying exchange order state to local live-order rows.

One place turns a Binance order payload (a placement response, an open-order
listing entry, or an order lookup) into local state, so the placement path and
the reconciliation path cannot drift apart. They used to: reconciliation copied
the status and filled quantity but never the fill price, and the risk book
ignores any row without a fill price, so an order that filled after it was
placed never became a position.
"""

from datetime import UTC, datetime
from typing import Any

from app.models.live_trading import LiveOrder


def apply_exchange_result(order: LiveOrder, result: dict[str, Any]) -> None:
    """Copy Binance's view of an order onto the local record."""
    if result.get("orderId"):
        order.exchange_order_id = str(result["orderId"])
    order.status = result.get("status") or order.status or "NEW"
    order.raw_response = result

    executed_qty = float(result.get("executedQty", 0) or 0)
    order.filled_quantity = executed_qty

    fills = result.get("fills") or []
    if fills:
        notional = sum(float(f["price"]) * float(f["qty"]) for f in fills)
        filled_qty = sum(float(f["qty"]) for f in fills)
        order.filled_price = notional / filled_qty if filled_qty else None
        order.commission = sum(float(f.get("commission", 0) or 0) for f in fills)
        order.commission_asset = fills[0].get("commissionAsset")
    elif executed_qty and float(result.get("cummulativeQuoteQty", 0) or 0) > 0:
        order.filled_price = float(result["cummulativeQuoteQty"]) / executed_qty

    stamp = result.get("transactTime") or result.get("updateTime")
    if stamp:
        order.transact_time = datetime.fromtimestamp(int(stamp) / 1000, tz=UTC)
