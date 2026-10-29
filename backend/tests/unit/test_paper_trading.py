"""
QuantX — Unit Tests for the Paper Trading Service & Fill Simulator.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.models.user import User
from app.schemas.paper_trading import CreatePaperAccountRequest, SubmitPaperOrderRequest
from app.services.paper_trading_service import PaperTradingService

# These tests exercise fills and bookkeeping with large round lots; the risk
# gate is covered separately in tests/unit/test_paper_risk_gate.py.
pytestmark = pytest.mark.usefixtures("relaxed_risk_limits")


@pytest.mark.unit
class TestPaperTradingService:
    """Account creation, fills, and ownership enforcement."""

    @pytest.mark.asyncio
    async def test_create_account(self, db_session: AsyncSession, test_user: User) -> None:
        """A new account starts with the requested balance."""
        service = PaperTradingService(db_session)
        acc = await service.create_account(
            test_user.id, CreatePaperAccountRequest(name="Test Paper Account", initial_balance=50000.0)
        )
        assert acc.name == "Test Paper Account"
        assert acc.initial_balance == 50000.0
        assert acc.current_balance == 50000.0

    @pytest.mark.asyncio
    async def test_buy_order_fills_and_updates_balance(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A BUY deducts notional plus fee and opens a position."""
        service = PaperTradingService(db_session)
        acc = await service.create_account(
            test_user.id, CreatePaperAccountRequest(initial_balance=100000.0)
        )

        order = await service.submit_order(
            test_user.id,
            SubmitPaperOrderRequest(
                account_id=acc.id, symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=1.0
            ),
            market_price=50000.0,
        )
        assert order.status == "FILLED"
        assert order.filled_price > 50000.0  # slippage works against the taker

        positions = await service.get_positions(test_user.id, acc.id)
        assert len(positions) == 1
        assert positions[0].symbol == "BTCUSDT"
        assert positions[0].quantity == 1.0
        assert acc.current_balance < 100000.0 - 50000.0  # notional plus fee

    @pytest.mark.asyncio
    async def test_sell_order_closes_position_and_realizes_pnl(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A SELL reduces the position, credits the account and books PnL.

        SELL was previously unimplemented: the order was recorded as FILLED
        while balance and position were left untouched, which minted money.
        """
        service = PaperTradingService(db_session)
        acc = await service.create_account(
            test_user.id, CreatePaperAccountRequest(initial_balance=100000.0)
        )
        req = {"account_id": acc.id, "symbol": "BTCUSDT", "order_type": "MARKET", "quantity": 1.0}

        await service.submit_order(
            test_user.id, SubmitPaperOrderRequest(side="BUY", **req), market_price=50000.0
        )
        balance_after_buy = acc.current_balance

        await service.submit_order(
            test_user.id, SubmitPaperOrderRequest(side="SELL", **req), market_price=60000.0
        )

        assert acc.current_balance > balance_after_buy
        assert acc.realized_pnl > 0
        assert await service.get_positions(test_user.id, acc.id) == []

    @pytest.mark.asyncio
    async def test_sell_without_position_is_rejected(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Selling something you do not hold is a validation error."""
        service = PaperTradingService(db_session)
        acc = await service.create_account(test_user.id, CreatePaperAccountRequest())

        with pytest.raises(ValidationError, match="No open position"):
            await service.submit_order(
                test_user.id,
                SubmitPaperOrderRequest(
                    account_id=acc.id, symbol="BTCUSDT", side="SELL", quantity=1.0
                ),
                market_price=50000.0,
            )

    @pytest.mark.asyncio
    async def test_oversell_is_rejected(self, db_session: AsyncSession, test_user: User) -> None:
        """Selling more than the position holds is rejected."""
        service = PaperTradingService(db_session)
        acc = await service.create_account(
            test_user.id, CreatePaperAccountRequest(initial_balance=100000.0)
        )
        await service.submit_order(
            test_user.id,
            SubmitPaperOrderRequest(account_id=acc.id, symbol="BTCUSDT", side="BUY", quantity=1.0),
            market_price=50000.0,
        )

        with pytest.raises(ValidationError, match="position holds only"):
            await service.submit_order(
                test_user.id,
                SubmitPaperOrderRequest(
                    account_id=acc.id, symbol="BTCUSDT", side="SELL", quantity=5.0
                ),
                market_price=50000.0,
            )

    @pytest.mark.asyncio
    async def test_insufficient_balance_is_rejected(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A BUY larger than the balance is rejected."""
        service = PaperTradingService(db_session)
        acc = await service.create_account(
            test_user.id, CreatePaperAccountRequest(initial_balance=1000.0)
        )
        with pytest.raises(ValidationError, match="Insufficient virtual balance"):
            await service.submit_order(
                test_user.id,
                SubmitPaperOrderRequest(
                    account_id=acc.id, symbol="BTCUSDT", side="BUY", quantity=1.0
                ),
                market_price=50000.0,
            )

    @pytest.mark.asyncio
    async def test_cannot_read_another_users_account(
        self, db_session: AsyncSession, test_user: User, second_user: User
    ) -> None:
        """Ownership is enforced on read.

        Without this check any authenticated user could read another user's
        account simply by supplying its UUID.
        """
        service = PaperTradingService(db_session)
        acc = await service.create_account(test_user.id, CreatePaperAccountRequest())

        with pytest.raises(AuthorizationError):
            await service.get_account(second_user.id, acc.id)
        with pytest.raises(AuthorizationError):
            await service.get_positions(second_user.id, acc.id)

    @pytest.mark.asyncio
    async def test_cannot_trade_another_users_account(
        self, db_session: AsyncSession, test_user: User, second_user: User
    ) -> None:
        """Ownership is enforced on write, not just on read."""
        service = PaperTradingService(db_session)
        acc = await service.create_account(
            test_user.id, CreatePaperAccountRequest(initial_balance=100000.0)
        )
        with pytest.raises(AuthorizationError):
            await service.submit_order(
                second_user.id,
                SubmitPaperOrderRequest(
                    account_id=acc.id, symbol="BTCUSDT", side="BUY", quantity=1.0
                ),
                market_price=50000.0,
            )

    @pytest.mark.asyncio
    async def test_missing_account_raises_not_found(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """An unknown account id is a 404, not an authorization failure."""
        with pytest.raises(NotFoundError):
            await PaperTradingService(db_session).get_account(test_user.id, uuid.uuid4())
