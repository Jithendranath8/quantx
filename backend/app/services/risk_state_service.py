"""
QuantX — Persistent Risk State Service.

The circuit breaker must survive process restarts and must be visible to every
uvicorn worker and Celery worker at once. Holding it in a Python attribute on a
per-request ``RiskManager`` means a kill switch flips a flag on an object that
is garbage-collected microseconds later, and a module-level instance is still
only one process out of N. This service is the single source of truth: the
``risk_state`` table, keyed by user.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.master_models import RiskState
from app.schemas.risk import RiskConfig

logger = get_logger(__name__)


class RiskStateService:
    """Reads and writes the durable per-user risk state."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, user_id: uuid.UUID) -> RiskState:
        """Fetch the user's risk state row, creating a default one if absent.

        Uses an idempotent upsert so two concurrent requests for a first-time
        user cannot race into a unique-constraint violation.
        """
        stmt = select(RiskState).where(RiskState.user_id == user_id)
        existing = (await self._session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return existing

        insert_stmt = (
            insert(RiskState)
            .values(user_id=user_id)
            .on_conflict_do_nothing(index_elements=["user_id"])
        )
        await self._session.execute(insert_stmt)
        await self._session.flush()
        return (await self._session.execute(stmt)).scalar_one()

    async def load_config(self, user_id: uuid.UUID, base: RiskConfig | None = None) -> RiskConfig:
        """Build a RiskConfig whose circuit breaker reflects persisted state."""
        state = await self.get_or_create(user_id)
        config = (base or RiskConfig()).model_copy()
        config.circuit_breaker_active = state.circuit_breaker_active
        return config

    async def set_circuit_breaker(
        self,
        user_id: uuid.UUID,
        active: bool,
        reason: str | None = None,
    ) -> RiskState:
        """Engage or release the circuit breaker durably.

        The caller is responsible for committing; this keeps the change atomic
        with whatever else the caller is writing (event ledger, order updates).
        """
        state = await self.get_or_create(user_id)
        state.circuit_breaker_active = active
        state.circuit_breaker_reason = reason if active else None
        state.updated_at = datetime.now(UTC)
        await self._session.flush()
        logger.warning(
            "circuit_breaker_state_changed",
            user_id=str(user_id),
            active=active,
            reason=reason,
        )
        return state

    async def is_halted(self, user_id: uuid.UUID) -> bool:
        """Check whether trading is currently halted for this user."""
        state = await self.get_or_create(user_id)
        return state.circuit_breaker_active

    async def record_daily_loss(self, user_id: uuid.UUID, loss_usd: float) -> RiskState:
        """Accumulate realized daily loss and stamp the last-loss time."""
        state = await self.get_or_create(user_id)
        state.daily_loss_usd = float(state.daily_loss_usd) + max(0.0, loss_usd)
        state.last_loss_timestamp = datetime.now(UTC)
        state.updated_at = datetime.now(UTC)
        await self._session.flush()
        return state

    async def reset_daily_loss(self, user_id: uuid.UUID) -> RiskState:
        """Reset the daily loss counter at the start of a new trading day."""
        state = await self.get_or_create(user_id)
        state.daily_loss_usd = 0.0
        state.updated_at = datetime.now(UTC)
        await self._session.flush()
        return state

    async def update_drawdown(self, user_id: uuid.UUID, portfolio_value: float) -> RiskState:
        """Track the portfolio peak and current drawdown percentage."""
        state = await self.get_or_create(user_id)
        if portfolio_value > state.peak_portfolio_value:
            state.peak_portfolio_value = portfolio_value
        peak = state.peak_portfolio_value or 1.0
        state.current_drawdown_pct = max(0.0, (peak - portfolio_value) / peak * 100.0)
        state.updated_at = datetime.now(UTC)
        await self._session.flush()
        return state
