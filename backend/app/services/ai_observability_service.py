"""
QuantX — AI Observability & Analytics Service.

Stores every AI decision with its model, latency, token usage and cost, and
computes aggregate metrics.

Aggregates are computed in SQL over a bounded time window. Loading the whole
``ai_decision_logs`` table into Python to sum it gets monotonically slower
forever and eventually exhausts memory.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Float, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.master_models import AIDecisionLog
from app.services.ai_outcome_service import SETTLEMENT_NOTIONAL_USD


class AIObservabilityService:
    """Service tracking AI decision metrics, validation rate, and token spend."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log_decision(
        self,
        model: str,
        input_snapshot: dict,
        output_decision: dict,
        confidence: float,
        action: str,
        latency_ms: int,
        token_usage: dict,
        estimated_cost_usd: float = 0.0,
        was_validated: bool = True,
        validation_rejection_reason: str | None = None,
        user_id: uuid.UUID | None = None,
        symbol: str | None = None,
    ) -> AIDecisionLog:
        """Persist one AI decision record."""
        log = AIDecisionLog(
            user_id=user_id,
            symbol=symbol.upper() if symbol else None,
            model=model,
            input_snapshot=input_snapshot,
            output_decision=output_decision,
            confidence=confidence,
            action=action,
            latency_ms=latency_ms,
            token_usage=token_usage or {},
            estimated_cost_usd=estimated_cost_usd,
            was_validated=was_validated,
            validation_rejection_reason=(
                validation_rejection_reason[:255] if validation_rejection_reason else None
            ),
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        return log

    async def get_analytics(
        self,
        user_id: uuid.UUID | None = None,
        window_days: int = 30,
    ) -> dict[str, Any]:
        """Compute AI performance metrics over a bounded window.

        Win rate and expectancy are derived from ``realized_pnl`` on decisions
        that have actually been settled. When nothing has settled yet they are
        reported as null with a zero sample count, rather than as a plausible
        looking constant.
        """
        since = datetime.now(UTC) - timedelta(days=max(1, window_days))

        filters = [AIDecisionLog.timestamp >= since]
        if user_id is not None:
            filters.append(AIDecisionLog.user_id == user_id)

        totals = (
            await self._session.execute(
                select(
                    func.count().label("total"),
                    func.avg(AIDecisionLog.latency_ms).label("avg_latency_ms"),
                    func.sum(AIDecisionLog.estimated_cost_usd).label("total_cost"),
                    func.sum(
                        cast(AIDecisionLog.token_usage["total_tokens"].astext, Float)
                    ).label("total_tokens"),
                    func.sum(case((AIDecisionLog.was_validated.is_(True), 1), else_=0)).label("validated"),
                    func.avg(AIDecisionLog.confidence).label("avg_confidence"),
                ).where(*filters)
            )
        ).one()

        total = int(totals.total or 0)
        if total == 0:
            return {
                "window_days": window_days,
                "total_ai_decisions": 0,
                "ai_win_rate_pct": None,
                "ai_expectancy_usd": None,
                "settled_decisions": 0,
                "avg_latency_ms": None,
                "avg_confidence": None,
                "total_tokens_used": 0,
                "total_cost_usd": 0.0,
                "validated_decisions_pct": None,
                "action_breakdown": {},
                "outcome_breakdown": {},
                "outcome_source": "SIGNAL_FORWARD_TEST",
                "settlement_notional_usd": SETTLEMENT_NOTIONAL_USD,
            }

        # Win rate is computed over *directional* settled decisions only.
        # Including WAIT decisions (which settle at exactly 0) would drag the
        # rate toward zero and describe nothing useful.
        settled = (
            await self._session.execute(
                select(
                    func.count().label("settled"),
                    func.sum(case((AIDecisionLog.realized_pnl > 0, 1), else_=0)).label("wins"),
                    func.avg(AIDecisionLog.realized_pnl).label("expectancy"),
                ).where(
                    *filters,
                    AIDecisionLog.realized_pnl.isnot(None),
                    AIDecisionLog.action.in_(["BUY", "SELL"]),
                )
            )
        ).one()

        outcomes = (
            await self._session.execute(
                select(AIDecisionLog.outcome_detail, func.count())
                .where(*filters, AIDecisionLog.outcome_detail.isnot(None))
                .group_by(AIDecisionLog.outcome_detail)
            )
        ).all()

        actions = (
            await self._session.execute(
                select(AIDecisionLog.action, func.count())
                .where(*filters)
                .group_by(AIDecisionLog.action)
            )
        ).all()

        settled_count = int(settled.settled or 0)
        return {
            "window_days": window_days,
            "total_ai_decisions": total,
            "ai_win_rate_pct": (
                round(int(settled.wins or 0) / settled_count * 100, 2) if settled_count else None
            ),
            "ai_expectancy_usd": (
                round(float(settled.expectancy), 2) if settled.expectancy is not None else None
            ),
            "settled_decisions": settled_count,
            "avg_latency_ms": int(totals.avg_latency_ms) if totals.avg_latency_ms is not None else None,
            "avg_confidence": (
                round(float(totals.avg_confidence), 3) if totals.avg_confidence is not None else None
            ),
            "total_tokens_used": int(totals.total_tokens or 0),
            "total_cost_usd": round(float(totals.total_cost or 0.0), 6),
            "validated_decisions_pct": round(int(totals.validated or 0) / total * 100, 1),
            "action_breakdown": {action: count for action, count in actions},
            "outcome_breakdown": {detail: count for detail, count in outcomes},
            # Names the method behind win rate and expectancy, so a forward
            # test is never mistaken for realized trading performance.
            "outcome_source": "SIGNAL_FORWARD_TEST",
            "settlement_notional_usd": SETTLEMENT_NOTIONAL_USD,
        }

    async def record_outcome(self, decision_id: uuid.UUID, realized_pnl: float) -> AIDecisionLog | None:
        """Attach a realized PnL to a past decision so win rate becomes real."""
        log = await self._session.get(AIDecisionLog, decision_id)
        if log is None:
            return None
        log.realized_pnl = realized_pnl
        await self._session.commit()
        return log

    async def list_decisions(
        self,
        user_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[AIDecisionLog]:
        """List recent AI decisions, newest first."""
        stmt = select(AIDecisionLog).order_by(AIDecisionLog.timestamp.desc())
        if user_id is not None:
            stmt = stmt.where(AIDecisionLog.user_id == user_id)
        stmt = stmt.limit(min(max(1, limit), 500))
        return list((await self._session.execute(stmt)).scalars().all())
