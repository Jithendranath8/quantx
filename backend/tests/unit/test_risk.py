"""
QuantX — Unit Tests for the Risk Engine.
"""

import pytest

from app.engines.risk.manager import RiskManager
from app.schemas.risk import RiskConfig, TradeRiskRequest


@pytest.fixture
def risk_manager() -> RiskManager:
    """RiskManager with standard limits."""
    return RiskManager(
        RiskConfig(
            max_risk_per_trade_pct=0.02,
            max_daily_loss_pct=0.05,
            max_leverage=10,
            max_portfolio_exposure_pct=0.50,
            max_concurrent_trades=5,
            circuit_breaker_active=False,
        )
    )


@pytest.mark.unit
class TestRiskManager:
    """Hard rule verification."""

    def test_approved_trade(self, risk_manager: RiskManager) -> None:
        """A trade inside every limit is approved."""
        res = risk_manager.validate_trade(
            TradeRiskRequest(
                symbol="BTCUSDT",
                action="BUY",
                account_balance=10000.0,
                order_amount_usd=1000.0,
                leverage=2,
                entry_price=50000.0,
                stop_loss_price=49000.0,
            )
        )
        assert res.is_approved is True
        assert res.rejection_reason is None

    def test_exceeded_leverage_rejected(self, risk_manager: RiskManager) -> None:
        """Leverage above the configured maximum is rejected."""
        res = risk_manager.validate_trade(
            TradeRiskRequest(
                symbol="BTCUSDT",
                action="BUY",
                account_balance=10000.0,
                order_amount_usd=1000.0,
                leverage=20,
                entry_price=50000.0,
            )
        )
        assert res.is_approved is False
        assert "Leverage 20x exceeds" in res.rejection_reason

    def test_exceeded_daily_loss_flags_circuit_breaker(self, risk_manager: RiskManager) -> None:
        """Breaching the daily loss limit reports a breaker trip to the caller."""
        res = risk_manager.validate_trade(
            TradeRiskRequest(
                symbol="BTCUSDT",
                action="BUY",
                account_balance=10000.0,
                order_amount_usd=1000.0,
                entry_price=50000.0,
                current_daily_loss_usd=600.0,  # Limit is 5% of 10k = $500
            )
        )
        assert res.is_approved is False
        assert res.circuit_breaker_triggered is True

    def test_validate_trade_does_not_mutate_config(self, risk_manager: RiskManager) -> None:
        """validate_trade is pure; persisting a halt is the caller's job.

        In-process mutation was invisible to other workers and lost on restart,
        so a tripped breaker silently stopped applying.
        """
        request = TradeRiskRequest(
            symbol="BTCUSDT",
            action="BUY",
            account_balance=10000.0,
            order_amount_usd=1000.0,
            entry_price=50000.0,
            current_daily_loss_usd=600.0,
        )
        risk_manager.validate_trade(request)
        assert risk_manager.config.circuit_breaker_active is False

        # And the decision is stable across repeated calls.
        assert risk_manager.validate_trade(request).circuit_breaker_triggered is True

    def test_active_circuit_breaker_blocks_everything(self) -> None:
        """A halted account cannot trade regardless of how small the order is."""
        manager = RiskManager(RiskConfig(circuit_breaker_active=True))
        res = manager.validate_trade(
            TradeRiskRequest(
                symbol="BTCUSDT",
                action="BUY",
                account_balance=100_000.0,
                order_amount_usd=1.0,
                entry_price=50000.0,
            )
        )
        assert res.is_approved is False
        assert res.circuit_breaker_triggered is True
        assert res.max_allowed_position_size_usd == 0.0

    def test_concurrent_trade_limit(self, risk_manager: RiskManager) -> None:
        """Position count at the cap blocks new entries."""
        res = risk_manager.validate_trade(
            TradeRiskRequest(
                symbol="BTCUSDT",
                action="BUY",
                account_balance=10000.0,
                order_amount_usd=100.0,
                entry_price=50000.0,
                active_positions_count=5,
            )
        )
        assert res.is_approved is False
        assert "Active position limit" in res.rejection_reason

    def test_portfolio_exposure_limit(self, risk_manager: RiskManager) -> None:
        """Exposure beyond the cap is rejected with the remaining headroom."""
        res = risk_manager.validate_trade(
            TradeRiskRequest(
                symbol="BTCUSDT",
                action="BUY",
                account_balance=10000.0,
                order_amount_usd=3000.0,
                entry_price=50000.0,
                current_exposure_usd=4000.0,  # 4000 + 3000 > 50% of 10000
            )
        )
        assert res.is_approved is False
        assert res.max_allowed_position_size_usd == pytest.approx(1000.0)
