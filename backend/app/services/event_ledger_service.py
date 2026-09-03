"""
QuantX — Immutable Event Ledger Service.

Records every market event, strategy signal, AI decision, validation result,
risk decision, order status change, position change, and kill switch activation.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.master_models import EventLedger


class EventLedgerService:
    """Service writing immutable audit trail events into the database."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log_event(
        self,
        source: str,
        event_type: str,
        payload: dict,
        user_id: uuid.UUID | None = None,
        account_id: uuid.UUID | None = None,
        symbol: str | None = None,
        correlation_id: str | None = None,
        commit: bool = True,
    ) -> EventLedger:
        """Create and persist an immutable event entry.

        Args:
            commit: When False the caller owns the transaction. Audit writes
                should usually be atomic with the action they describe, so a
                caller mid-transaction passes False and commits once at the end.
        """
        event = EventLedger(
            event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
            timestamp=datetime.now(UTC),
            user_id=user_id,
            account_id=account_id,
            symbol=symbol.upper() if symbol else None,
            source=source,
            event_type=event_type,
            payload=payload,
            correlation_id=correlation_id or uuid.uuid4().hex[:16],
        )
        self._session.add(event)
        await self._session.flush()
        if commit:
            await self._session.commit()
            await self._session.refresh(event)
        return event

    async def list_events(
        self,
        user_id: uuid.UUID | None = None,
        event_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EventLedger]:
        """List ledger entries newest first, always bounded by a limit."""
        stmt = select(EventLedger).order_by(EventLedger.timestamp.desc())
        if user_id is not None:
            stmt = stmt.where(EventLedger.user_id == user_id)
        if event_type is not None:
            stmt = stmt.where(EventLedger.event_type == event_type)
        stmt = stmt.offset(max(0, offset)).limit(min(max(1, limit), 500))
        return list((await self._session.execute(stmt)).scalars().all())
