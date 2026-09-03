"""
QuantX — Event Ledger API Endpoints.

Read access to the immutable audit trail. Entries are always scoped to the
requesting user and bounded by a limit; the ledger is append-only and grows
until the retention worker prunes it.
"""

from typing import Any

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser, DBSession
from app.services.event_ledger_service import EventLedgerService

router = APIRouter(prefix="/events", tags=["Event Ledger"])


@router.get(
    "",
    summary="List your event ledger entries",
)
async def list_events(
    user: CurrentUser,
    db: DBSession,
    event_type: str | None = Query(None, max_length=50),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    """Return audit-trail entries for the authenticated user, newest first."""
    events = await EventLedgerService(db).list_events(
        user_id=user.id, event_type=event_type, limit=limit, offset=offset
    )
    return [
        {
            "event_id": e.event_id,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "source": e.source,
            "event_type": e.event_type,
            "symbol": e.symbol,
            "payload": e.payload,
            "correlation_id": e.correlation_id,
        }
        for e in events
    ]
