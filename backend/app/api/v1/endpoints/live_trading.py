"""
QuantX — Live Trading API Endpoints.

Order execution and the emergency kill switch. Every route here can move real
funds or halt trading, so all of them require authentication; none of them did
before.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import CurrentUser, DBSession, RateLimiter
from app.schemas.live_trading import LiveOrderRequest, LiveOrderResponse
from app.services.kill_switch import KillSwitchService
from app.services.live_trading_service import LiveTradingService

router = APIRouter(prefix="/live", tags=["Live Trading Engine"])


@router.post(
    "/orders",
    response_model=LiveOrderResponse,
    status_code=201,
    summary="Execute a live order on Binance",
    dependencies=[Depends(RateLimiter("live_orders", max_requests=30))],
)
async def execute_order(
    req: LiveOrderRequest,
    user: CurrentUser,
    db: DBSession,
) -> LiveOrderResponse:
    """Place a live order after mandatory risk-engine validation.

    Mainnet execution additionally requires ALLOW_MAINNET_TRADING=true.
    """
    return await LiveTradingService(db).execute_live_order(user_id=user.id, req=req)


@router.get(
    "/orders",
    summary="List your live orders",
)
async def list_orders(
    user: CurrentUser,
    db: DBSession,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict[str, Any]]:
    """Return this user's live orders, newest first."""
    orders = await LiveTradingService(db).list_orders(user.id, limit=limit)
    return [
        {
            "id": str(o.id),
            "client_order_id": o.client_order_id,
            "exchange_order_id": o.exchange_order_id,
            "symbol": o.symbol,
            "side": o.side,
            "order_type": o.order_type,
            "quantity": o.quantity,
            "price": o.price,
            "status": o.status,
            "filled_quantity": o.filled_quantity,
            "filled_price": o.filled_price,
            "commission": o.commission,
            "is_testnet": o.is_testnet,
            "rejection_reason": o.rejection_reason,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in orders
    ]


@router.delete(
    "/orders/{order_id}",
    summary="Cancel one of your live orders",
)
async def cancel_order(
    order_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> dict[str, Any]:
    """Cancel a live order on the exchange."""
    order = await LiveTradingService(db).cancel_order(user.id, order_id)
    return {"id": str(order.id), "status": order.status, "symbol": order.symbol}


@router.post(
    "/kill-switch",
    summary="Trigger the emergency kill switch",
    dependencies=[Depends(RateLimiter("kill_switch", max_requests=10))],
)
async def trigger_kill_switch(
    user: CurrentUser,
    db: DBSession,
    reason: str = Query("EMERGENCY_USER_ACTIVATED", max_length=255),
) -> dict[str, Any]:
    """Halt trading, cancel open orders, and verify the cancellations.

    ``fully_successful`` is false if any exchange cancellation could not be
    confirmed — check it before assuming you are flat.
    """
    return await KillSwitchService(db).activate_kill_switch(user_id=user.id, reason=reason)


@router.post(
    "/kill-switch/deactivate",
    summary="Release the kill switch and resume trading",
)
async def deactivate_kill_switch(
    user: CurrentUser,
    db: DBSession,
    reason: str = Query("MANUAL_RESET", max_length=255),
) -> dict[str, Any]:
    """Clear the persisted circuit breaker for this user."""
    return await KillSwitchService(db).deactivate_kill_switch(user_id=user.id, reason=reason)


@router.get(
    "/kill-switch/status",
    summary="Current halt state",
)
async def kill_switch_status(user: CurrentUser, db: DBSession) -> dict[str, Any]:
    """Report whether trading is currently halted for this user."""
    return await KillSwitchService(db).get_status(user.id)
