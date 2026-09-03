"""
QuantX — Trade Journal REST API Endpoints.

Ownership is enforced in the service layer: every read filters on
``resource.user_id == current_user.id``.
"""

import uuid

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser, DBSession
from app.schemas.journal import CreateJournalEntryRequest, JournalEntrySchema
from app.services.journal_service import TradeJournalService

router = APIRouter(prefix="/journal", tags=["Trade Journal"])


@router.post(
    "",
    response_model=JournalEntrySchema,
    status_code=201,
    summary="Create a trade journal entry",
)
async def create_journal_entry(
    req: CreateJournalEntryRequest,
    user: CurrentUser,
    db: DBSession,
) -> JournalEntrySchema:
    """Create a journal record owned by the authenticated user."""
    entry = await TradeJournalService(db).create_entry(user_id=user.id, req=req)
    return JournalEntrySchema.model_validate(entry)


@router.get(
    "",
    response_model=list[JournalEntrySchema],
    summary="Get your trade journal entries",
)
async def get_user_journal_entries(
    user: CurrentUser,
    db: DBSession,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[JournalEntrySchema]:
    """Fetch a page of your journal entries, newest first."""
    entries = await TradeJournalService(db).get_user_entries(
        user_id=user.id, limit=limit, offset=offset
    )
    return [JournalEntrySchema.model_validate(e) for e in entries]


@router.get(
    "/count",
    summary="Count your trade journal entries",
)
async def count_journal_entries(user: CurrentUser, db: DBSession) -> dict[str, int]:
    """Total journal entries you own, for pagination."""
    return {"total": await TradeJournalService(db).count_user_entries(user.id)}


@router.get(
    "/{journal_id}",
    response_model=JournalEntrySchema,
    summary="Get a trade journal entry by ID",
)
async def get_journal_entry_by_id(
    journal_id: uuid.UUID,
    user: CurrentUser,
    db: DBSession,
) -> JournalEntrySchema:
    """Fetch a single entry, verifying you own it."""
    entry = await TradeJournalService(db).get_entry_by_id(user_id=user.id, journal_id=journal_id)
    return JournalEntrySchema.model_validate(entry)
