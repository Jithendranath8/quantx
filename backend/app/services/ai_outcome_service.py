"""
QuantX — AI Decision Outcome Settlement.

Attributes an outcome to each past AI decision so that win rate and expectancy
become measurements instead of nulls.

Method
------
Settlement is a **forward test on stored candles**, not a record of money made.
For a decision at time T with an entry, stop and target, subsequent candles are
walked to see which level the market reached first. When both fall inside one
bar the stop is assumed to trigger, matching the backtester and keeping the
result conservative — assuming the target instead would flatter every number.

The outcome is recorded with ``outcome_source='SIGNAL_FORWARD_TEST'`` so it can
never be mistaken for a realized trading result. PnL is expressed for a fixed
``SETTLEMENT_NOTIONAL_USD`` of notional so decisions are comparable to one
another regardless of the price of the underlying.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.market_data import Candle
from app.models.master_models import AIDecisionLog

logger = get_logger(__name__)

SETTLEMENT_NOTIONAL_USD = 1_000.0
OUTCOME_SOURCE = "SIGNAL_FORWARD_TEST"
# How long a signal is given to resolve before it is marked to market.
DEFAULT_HORIZON_HOURS = 48
# A decision younger than this has not had time to play out.
MIN_AGE_HOURS = 1
SETTLEMENT_TIMEFRAME = "1h"


class AIOutcomeService:
    """Settles AI decisions against subsequent price action."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def settle_pending(
        self,
        limit: int = 200,
        horizon_hours: int = DEFAULT_HORIZON_HOURS,
    ) -> dict[str, int]:
        """Settle decisions that are old enough and have no outcome yet.

        Returns:
            Counts of settled, skipped (insufficient data) and non-actionable
            decisions.
        """
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=MIN_AGE_HOURS)

        stmt = (
            select(AIDecisionLog)
            .where(
                AIDecisionLog.realized_pnl.is_(None),
                AIDecisionLog.timestamp <= cutoff,
            )
            .order_by(AIDecisionLog.timestamp.asc())
            .limit(min(max(1, limit), 1000))
        )
        decisions = list((await self._session.execute(stmt)).scalars().all())

        settled = skipped = non_actionable = 0
        for decision in decisions:
            result = await self._settle_one(decision, horizon_hours, now)
            if result == "settled":
                settled += 1
            elif result == "non_actionable":
                non_actionable += 1
            else:
                skipped += 1

        if settled or non_actionable:
            await self._session.commit()

        logger.info(
            "ai_decisions_settled",
            settled=settled,
            non_actionable=non_actionable,
            skipped=skipped,
        )
        return {"settled": settled, "non_actionable": non_actionable, "skipped": skipped}

    async def settle_decision(self, decision_id: uuid.UUID) -> AIDecisionLog | None:
        """Settle a single decision by id, if it can be resolved."""
        decision = await self._session.get(AIDecisionLog, decision_id)
        if decision is None:
            return None
        await self._settle_one(decision, DEFAULT_HORIZON_HOURS, datetime.now(UTC))
        await self._session.commit()
        return decision

    # ── Internals ────────────────────────────────────────────────────

    async def _settle_one(
        self,
        decision: AIDecisionLog,
        horizon_hours: int,
        now: datetime,
    ) -> str:
        """Resolve one decision. Returns 'settled', 'skipped' or 'non_actionable'."""
        # WAIT carries no market exposure, so its outcome is exactly zero. It
        # is recorded rather than left null, otherwise the settled-count would
        # only ever reflect directional calls.
        if decision.action not in {"BUY", "SELL"}:
            decision.realized_pnl = 0.0
            decision.outcome_source = OUTCOME_SOURCE
            decision.outcome_detail = "NO_POSITION"
            decision.settled_at = now
            return "non_actionable"

        output = decision.output_decision or {}
        entry = _as_float(output.get("entry_price"))
        stop = _as_float(output.get("stop_loss"))
        target = _as_float(output.get("take_profit"))
        symbol = decision.symbol

        if not symbol or entry is None or entry <= 0:
            return "skipped"

        horizon_end = decision.timestamp + timedelta(hours=horizon_hours)
        if now < horizon_end and (stop is None or target is None):
            # Without levels the only resolution is the horizon close, which
            # has not arrived yet.
            return "skipped"

        candles = await self._candles_after(symbol, decision.timestamp, horizon_end)
        if not candles:
            return "skipped"

        exit_price, detail = self._resolve_exit(
            action=decision.action, entry=entry, stop=stop, target=target, candles=candles
        )
        if exit_price is None:
            if now < horizon_end:
                return "skipped"
            exit_price, detail = candles[-1].close, "HORIZON_CLOSE"

        direction = 1.0 if decision.action == "BUY" else -1.0
        quantity = SETTLEMENT_NOTIONAL_USD / entry
        decision.realized_pnl = round((exit_price - entry) * quantity * direction, 4)
        decision.outcome_source = OUTCOME_SOURCE
        decision.outcome_detail = detail
        decision.settled_at = now
        return "settled"

    async def _candles_after(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """Load candles strictly after the decision, up to the horizon."""
        stmt = (
            select(Candle)
            .where(
                Candle.symbol == symbol.upper(),
                Candle.timeframe == SETTLEMENT_TIMEFRAME,
                Candle.timestamp > start,
                Candle.timestamp <= end,
            )
            .order_by(Candle.timestamp.asc())
            .limit(2000)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    @staticmethod
    def _resolve_exit(
        action: str,
        entry: float,
        stop: float | None,
        target: float | None,
        candles: list[Candle],
    ) -> tuple[float | None, str]:
        """Find the first level the market reached, if any.

        Stop is checked before target within a bar: from OHLC alone we cannot
        know which came first, and assuming the favourable one would inflate
        every reported win rate.
        """
        for candle in candles:
            if action == "BUY":
                if stop is not None and candle.low <= stop:
                    return stop, "STOP_LOSS"
                if target is not None and candle.high >= target:
                    return target, "TAKE_PROFIT"
            else:
                if stop is not None and candle.high >= stop:
                    return stop, "STOP_LOSS"
                if target is not None and candle.low <= target:
                    return target, "TAKE_PROFIT"
        return None, ""


def _as_float(value: object) -> float | None:
    """Coerce a JSON value to float, returning None when absent or unusable."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
