"""
QuantX — Unit Tests for AI decision settlement.

Win rate and expectancy were permanently null because nothing ever attributed
an outcome to a decision. These tests pin the settlement method and, just as
importantly, its provenance labelling.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data import Candle
from app.models.master_models import AIDecisionLog
from app.services.ai_observability_service import AIObservabilityService
from app.services.ai_outcome_service import (
    OUTCOME_SOURCE,
    SETTLEMENT_NOTIONAL_USD,
    AIOutcomeService,
)

DECISION_TIME = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
ENTRY = 50_000.0


def candle(hours_after: int, high: float, low: float, close: float) -> Candle:
    """A 1h candle at a fixed offset from the decision."""
    ts = DECISION_TIME + timedelta(hours=hours_after)
    return Candle(
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp=ts,
        open=close,
        high=high,
        low=low,
        close=close,
        volume=10.0,
        close_time=ts + timedelta(minutes=59),
        quote_volume=1000.0,
        trades_count=5,
        is_closed=True,
    )


def decision(action: str, stop: float | None, target: float | None) -> AIDecisionLog:
    """An unsettled AI decision at the anchor time."""
    return AIDecisionLog(
        symbol="BTCUSDT",
        model="test-model",
        confidence=0.8,
        action=action,
        latency_ms=120,
        token_usage={"total_tokens": 400},
        estimated_cost_usd=0.001,
        input_snapshot={},
        output_decision={
            "action": action,
            "entry_price": ENTRY,
            "stop_loss": stop,
            "take_profit": target,
        },
        timestamp=DECISION_TIME,
    )


@pytest.mark.unit
class TestSettlement:
    """Forward-testing a decision against subsequent candles."""

    @pytest.mark.asyncio
    async def test_take_profit_is_a_win(self, db_session: AsyncSession) -> None:
        """A BUY whose target is reached settles positive."""
        db_session.add_all([candle(1, 50_200, 49_900, 50_150), candle(2, 51_000, 50_100, 50_900)])
        db_session.add(decision("BUY", stop=49_000.0, target=50_500.0))
        await db_session.commit()

        assert (await AIOutcomeService(db_session).settle_pending())["settled"] == 1

        settled = (await db_session.execute(select(AIDecisionLog))).scalar_one()
        assert settled.outcome_detail == "TAKE_PROFIT"
        assert settled.outcome_source == OUTCOME_SOURCE
        # +1% on a $1,000 notional.
        assert settled.realized_pnl == pytest.approx(10.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_stop_loss_is_a_loss(self, db_session: AsyncSession) -> None:
        """A BUY whose stop is breached settles negative."""
        db_session.add(candle(1, 50_100, 49_400, 49_500))
        db_session.add(decision("BUY", stop=49_500.0, target=52_000.0))
        await db_session.commit()

        await AIOutcomeService(db_session).settle_pending()
        settled = (await db_session.execute(select(AIDecisionLog))).scalar_one()
        assert settled.outcome_detail == "STOP_LOSS"
        assert settled.realized_pnl == pytest.approx(-10.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_stop_wins_a_tie_inside_one_bar(self, db_session: AsyncSession) -> None:
        """When one bar spans both levels the stop is assumed to trigger.

        OHLC cannot say which came first, and assuming the target would inflate
        every reported win rate.
        """
        db_session.add(candle(1, 52_000, 49_000, 51_000))
        db_session.add(decision("BUY", stop=49_500.0, target=51_500.0))
        await db_session.commit()

        await AIOutcomeService(db_session).settle_pending()
        settled = (await db_session.execute(select(AIDecisionLog))).scalar_one()
        assert settled.outcome_detail == "STOP_LOSS"
        assert settled.realized_pnl < 0

    @pytest.mark.asyncio
    async def test_short_direction_is_inverted(self, db_session: AsyncSession) -> None:
        """A SELL profits when price falls to its target."""
        db_session.add(candle(1, 50_100, 49_000, 49_200))
        db_session.add(decision("SELL", stop=51_000.0, target=49_500.0))
        await db_session.commit()

        await AIOutcomeService(db_session).settle_pending()
        settled = (await db_session.execute(select(AIDecisionLog))).scalar_one()
        assert settled.outcome_detail == "TAKE_PROFIT"
        assert settled.realized_pnl > 0

    @pytest.mark.asyncio
    async def test_wait_settles_flat_and_is_labelled(self, db_session: AsyncSession) -> None:
        """WAIT carries no exposure, so its outcome is exactly zero."""
        db_session.add(decision("WAIT", stop=None, target=None))
        await db_session.commit()

        result = await AIOutcomeService(db_session).settle_pending()
        assert result["non_actionable"] == 1

        settled = (await db_session.execute(select(AIDecisionLog))).scalar_one()
        assert settled.realized_pnl == 0.0
        assert settled.outcome_detail == "NO_POSITION"

    @pytest.mark.asyncio
    async def test_unresolved_within_horizon_is_skipped(self, db_session: AsyncSession) -> None:
        """A decision that has not resolved yet stays unsettled."""
        recent = datetime.now(UTC) - timedelta(hours=2)
        log = decision("BUY", stop=40_000.0, target=60_000.0)
        log.timestamp = recent
        db_session.add(log)
        await db_session.commit()

        result = await AIOutcomeService(db_session).settle_pending()
        assert result["skipped"] == 1

        unsettled = (await db_session.execute(select(AIDecisionLog))).scalar_one()
        assert unsettled.realized_pnl is None

    @pytest.mark.asyncio
    async def test_settlement_is_not_repeated(self, db_session: AsyncSession) -> None:
        """A settled decision is not picked up again."""
        db_session.add(candle(1, 51_000, 49_900, 50_900))
        db_session.add(decision("BUY", stop=49_000.0, target=50_500.0))
        await db_session.commit()

        service = AIOutcomeService(db_session)
        assert (await service.settle_pending())["settled"] == 1
        assert (await service.settle_pending())["settled"] == 0

    @pytest.mark.asyncio
    async def test_too_recent_decisions_are_left_alone(self, db_session: AsyncSession) -> None:
        """A decision made moments ago has not had time to play out."""
        log = decision("BUY", stop=49_000.0, target=50_500.0)
        log.timestamp = datetime.now(UTC)
        db_session.add(log)
        await db_session.commit()

        result = await AIOutcomeService(db_session).settle_pending()
        assert result == {"settled": 0, "non_actionable": 0, "skipped": 0}


@pytest.mark.unit
class TestObservabilityAfterSettlement:
    """Metrics stop being null once decisions settle."""

    @pytest.mark.asyncio
    async def test_win_rate_excludes_wait_decisions(self, db_session: AsyncSession) -> None:
        """WAIT settles at zero but must not drag the win rate down.

        Counting non-directional calls as losses would describe nothing useful.
        """
        db_session.add_all([candle(1, 51_000, 49_900, 50_900), candle(2, 51_500, 50_500, 51_400)])
        db_session.add_all(
            [
                decision("BUY", stop=49_000.0, target=50_500.0),  # win
                decision("BUY", stop=49_950.0, target=99_000.0),  # loss
                decision("WAIT", stop=None, target=None),         # excluded
            ]
        )
        await db_session.commit()

        await AIOutcomeService(db_session).settle_pending()
        analytics = await AIObservabilityService(db_session).get_analytics(window_days=3650)

        assert analytics["settled_decisions"] == 2
        assert analytics["ai_win_rate_pct"] == pytest.approx(50.0)
        assert analytics["outcome_source"] == OUTCOME_SOURCE
        assert analytics["settlement_notional_usd"] == SETTLEMENT_NOTIONAL_USD
        assert analytics["outcome_breakdown"]["NO_POSITION"] == 1

    @pytest.mark.asyncio
    async def test_metrics_are_null_before_settlement(self, db_session: AsyncSession) -> None:
        """An unsettled decision leaves win rate null rather than guessed."""
        log = decision("BUY", stop=49_000.0, target=50_500.0)
        log.timestamp = datetime.now(UTC)
        db_session.add(log)
        await db_session.commit()

        analytics = await AIObservabilityService(db_session).get_analytics(window_days=3650)
        assert analytics["total_ai_decisions"] == 1
        assert analytics["ai_win_rate_pct"] is None
        assert analytics["ai_expectancy_usd"] is None
