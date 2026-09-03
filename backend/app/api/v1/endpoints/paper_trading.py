"""
QuantX — Paper Trading API Endpoints.

Virtual accounts, simulated orders, and positions. Every account-scoped route
resolves the account through the service, which enforces
``account.user_id == current_user.id``.
"""

import uuid

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser, DBSession
from app.schemas.paper_trading import (
    CreatePaperAccountRequest,
    PaperAccountSchema,
    PaperOrderSchema,
    PaperPositionSchema,
    SubmitPaperOrderRequest,
)
from app.services.paper_trading_service import PaperTradingService

router = APIRouter(prefix="/paper", tags=["Paper Trading Engine"])


@router.post(
    "/accounts",
    response_model=PaperAccountSchema,
    status_code=201,
    summary="Create a virtual paper trading account",
)
async def create_account(
    req: CreatePaperAccountRequest,
    user: CurrentUser,
    db: DBSession,
) -> PaperAccountSchema:
    """Create a new virtual paper account for the current user."""
    account = await PaperTradingService(db).create_account(user_id=user.id, req=req)
    return PaperAccountSchema.model_validate(account)


@router.get(
    "/accounts",
    response_model=list[PaperAccountSchema],
    summary="List your paper trading accounts",
)
async def list_accounts(user: CurrentUser, db: DBSession) -> list[PaperAccountSchema]:
    """List every paper account owned by the current user."""
    accounts = await PaperTradingService(db).list_accounts(user.id)
    return [PaperAccountSchema.model_validate(a) for a in accounts]


@router.get(
    "/accounts/{account_id}",
    response_model=PaperAccountSchema,
    summary="Get paper account details",
)
async def get_account(
    account_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> PaperAccountSchema:
    """Fetch balances and PnL for an account you own."""
    account = await PaperTradingService(db).get_account(user.id, account_id)
    return PaperAccountSchema.model_validate(account)


@router.post(
    "/orders",
    response_model=PaperOrderSchema,
    status_code=201,
    summary="Submit a paper order",
)
async def submit_paper_order(
    req: SubmitPaperOrderRequest,
    user: CurrentUser,
    db: DBSession,
) -> PaperOrderSchema:
    """Submit a paper order and simulate its fill against the live price."""
    order = await PaperTradingService(db).submit_order(user_id=user.id, req=req)
    return PaperOrderSchema.model_validate(order)


@router.get(
    "/accounts/{account_id}/positions",
    response_model=list[PaperPositionSchema],
    summary="Get open positions for a paper account",
)
async def get_positions(
    account_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> list[PaperPositionSchema]:
    """Fetch open positions for an account you own."""
    positions = await PaperTradingService(db).get_positions(user.id, account_id)
    return [PaperPositionSchema.model_validate(p) for p in positions]


@router.get(
    "/accounts/{account_id}/orders",
    response_model=list[PaperOrderSchema],
    summary="Get order history for a paper account",
)
async def get_orders(
    account_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
    limit: int = Query(100, ge=1, le=500),
) -> list[PaperOrderSchema]:
    """Fetch recent orders for an account you own."""
    orders = await PaperTradingService(db).get_orders(user.id, account_id, limit=limit)
    return [PaperOrderSchema.model_validate(o) for o in orders]


@router.get(
    "/accounts/{account_id}/pending",
    response_model=list[PaperOrderSchema],
    summary="List resting orders for a paper account",
)
async def get_pending_orders(
    account_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> list[PaperOrderSchema]:
    """Fetch LIMIT / STOP_LOSS / TAKE_PROFIT orders waiting to trigger."""
    orders = await PaperTradingService(db).get_pending_orders(user.id, account_id)
    return [PaperOrderSchema.model_validate(o) for o in orders]


@router.delete(
    "/orders/{order_id}",
    response_model=PaperOrderSchema,
    summary="Cancel a resting paper order",
)
async def cancel_paper_order(
    order_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> PaperOrderSchema:
    """Cancel an order that has not yet filled."""
    order = await PaperTradingService(db).cancel_order(user.id, order_id)
    return PaperOrderSchema.model_validate(order)


@router.post(
    "/accounts/{account_id}/process-pending",
    summary="Trigger any resting orders the market has reached",
)
async def process_pending(
    account_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> dict[str, int]:
    """Run the fill engine for this account on demand.

    A Celery worker does this every minute; this endpoint exists so the UI can
    reflect a trigger immediately rather than waiting for the next tick.
    """
    service = PaperTradingService(db)
    await service.get_account(user.id, account_id)
    return await service.process_pending_orders(account_id=account_id)


@router.post(
    "/accounts/{account_id}/mark-to-market",
    response_model=list[PaperPositionSchema],
    summary="Refresh position prices and unrealized PnL",
)
async def mark_to_market(
    account_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> list[PaperPositionSchema]:
    """Re-price open positions against the live market."""
    positions = await PaperTradingService(db).mark_to_market(user.id, account_id)
    return [PaperPositionSchema.model_validate(p) for p in positions]
