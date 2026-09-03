"""
QuantX — Unit Tests for the Portfolio Service.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.paper_trading import CreatePaperAccountRequest, SubmitPaperOrderRequest
from app.services.paper_trading_service import PaperTradingService
from app.services.portfolio_service import PortfolioService


@pytest.mark.unit
class TestPortfolioService:
    """Portfolio aggregation and export scoping."""

    @pytest.mark.asyncio
    async def test_no_accounts_returns_empty_portfolio(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A user with no accounts has an empty portfolio, not an invented one.

        This previously returned a fabricated $100,000 balance and a 65% win
        rate for anyone who had never traded.
        """
        summary = await PortfolioService(db_session).get_portfolio_summary(test_user.id)

        assert summary.total_equity_usd == 0.0
        assert summary.cash_balance_usd == 0.0
        assert summary.realized_pnl_usd == 0.0
        assert summary.win_rate_pct is None
        assert summary.allocations == []

    @pytest.mark.asyncio
    async def test_summary_reflects_real_balances(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Equity and allocations come from actual account rows."""
        paper = PaperTradingService(db_session)
        await paper.create_account(
            test_user.id, CreatePaperAccountRequest(initial_balance=25_000.0)
        )

        summary = await PortfolioService(db_session).get_portfolio_summary(test_user.id)
        assert summary.cash_balance_usd == pytest.approx(25_000.0)
        assert summary.total_equity_usd == pytest.approx(25_000.0)
        assert summary.open_positions_count == 0

    @pytest.mark.asyncio
    async def test_win_rate_is_computed_from_closed_positions(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Win rate appears only once a position has actually closed."""
        paper = PaperTradingService(db_session)
        acc = await paper.create_account(
            test_user.id, CreatePaperAccountRequest(initial_balance=100_000.0)
        )
        base = {"account_id": acc.id, "symbol": "BTCUSDT", "quantity": 1.0}
        await paper.submit_order(
            test_user.id, SubmitPaperOrderRequest(side="BUY", **base), market_price=50_000.0
        )
        await paper.submit_order(
            test_user.id, SubmitPaperOrderRequest(side="SELL", **base), market_price=60_000.0
        )

        summary = await PortfolioService(db_session).get_portfolio_summary(test_user.id)
        assert summary.closed_trades_count == 1
        assert summary.win_rate_pct == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_csv_export_only_contains_your_own_orders(
        self, db_session: AsyncSession, test_user: User, second_user: User
    ) -> None:
        """The export is scoped to the caller.

        It previously ran an unfiltered select(PaperOrder), returning every
        user's orders to anyone who asked.
        """
        paper = PaperTradingService(db_session)
        mine = await paper.create_account(
            test_user.id, CreatePaperAccountRequest(initial_balance=100_000.0)
        )
        theirs = await paper.create_account(
            second_user.id, CreatePaperAccountRequest(initial_balance=100_000.0)
        )
        await paper.submit_order(
            test_user.id,
            SubmitPaperOrderRequest(account_id=mine.id, symbol="BTCUSDT", side="BUY", quantity=1.0),
            market_price=50_000.0,
        )
        await paper.submit_order(
            second_user.id,
            SubmitPaperOrderRequest(account_id=theirs.id, symbol="ETHUSDT", side="BUY", quantity=1.0),
            market_price=3_000.0,
        )

        csv_text = "".join(
            [chunk async for chunk in PortfolioService(db_session).stream_trades_csv(test_user.id)]
        )
        assert "BTCUSDT" in csv_text
        assert "ETHUSDT" not in csv_text
        assert str(theirs.id) not in csv_text
