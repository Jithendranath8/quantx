"""
QuantX — Trade Journal Service (Phase 21 Architecture).

Provides full CRUD operations for Trade Journal entries including notes,
lessons learned, indicator/orderbook snapshots, tags, and PnL logs.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.master_models import TradeJournal
from app.schemas.journal import CreateJournalEntryRequest


class TradeJournalService:
    """Service managing Trade Journal records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_entry(self, user_id: uuid.UUID, req: CreateJournalEntryRequest) -> TradeJournal:
        """Create a new trade journal entry."""
        trade_id = f"TRD-{uuid.uuid4().hex[:10].upper()}"
        entry = TradeJournal(
            user_id=user_id,
            trade_id=trade_id,
            symbol=req.symbol.upper(),
            timeframe=req.timeframe,
            direction=req.direction.upper(),
            entry_price=req.entry_price,
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
            risk_reward=req.risk_reward,
            market_structure=req.market_structure,
            indicators_snapshot=req.indicators_snapshot,
            orderbook_snapshot=req.orderbook_snapshot,
            ai_reasoning=req.ai_reasoning,
            realized_pnl=req.realized_pnl,
            user_notes=req.user_notes,
            lessons=req.lessons,
            tags=req.tags or [],
        )
        self._session.add(entry)
        await self._session.commit()
        await self._session.refresh(entry)
        return entry

    async def get_user_entries(
        self,
        user_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TradeJournal]:
        """Fetch trade journal entries for the authenticated user, newest first.

        Always bounded: an unpaginated listing degrades linearly as the journal
        grows and eventually times out the request.
        """
        stmt = (
            select(TradeJournal)
            .where(TradeJournal.user_id == user_id)
            .order_by(TradeJournal.created_at.desc())
            .offset(max(0, offset))
            .limit(min(max(1, limit), 500))
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def count_user_entries(self, user_id: uuid.UUID) -> int:
        """Total journal entries owned by the user."""
        stmt = select(func.count()).select_from(TradeJournal).where(TradeJournal.user_id == user_id)
        return int((await self._session.execute(stmt)).scalar_one())

    async def get_entry_by_id(self, user_id: uuid.UUID, journal_id: uuid.UUID) -> TradeJournal:
        """Fetch single entry by ID and verify ownership."""
        stmt = select(TradeJournal).where(TradeJournal.id == journal_id, TradeJournal.user_id == user_id)
        res = await self._session.execute(stmt)
        entry = res.scalar_one_or_none()
        if not entry:
            raise NotFoundError("Trade journal entry", str(journal_id))
        return entry
