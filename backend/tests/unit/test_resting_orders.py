"""
QuantX — Unit Tests for resting paper orders.

Paper trading previously simulated MARKET fills only. LIMIT, STOP_LOSS and
TAKE_PROFIT orders now rest until the market reaches their level.
"""

from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.user import User
from app.schemas.paper_trading import CreatePaperAccountRequest, SubmitPaperOrderRequest
from app.services.paper_trading_service import PaperTradingService


class MovablePriceClient:
    """A market whose price the test controls."""

    testnet = True

    def __init__(self, price: float = 50_000.0) -> None:
        self.price = price

    async def get_price(self, symbol: str) -> float:
        return self.price


async def account_with_balance(
    session: AsyncSession, user: User, balance: float = 100_000.0
) -> Any:
    """Create a funded paper account."""
    service = PaperTradingService(session, client=MovablePriceClient())
    return await service.create_account(user.id, CreatePaperAccountRequest(initial_balance=balance))


@pytest.mark.unit
class TestOrderValidation:
    """Incomplete orders are rejected at the schema boundary."""

    def test_limit_requires_a_price(self) -> None:
        """A LIMIT with no price cannot be interpreted."""
        with pytest.raises(PydanticValidationError, match="require a price"):
            SubmitPaperOrderRequest(
                account_id="00000000-0000-0000-0000-000000000000",
                symbol="BTCUSDT",
                side="BUY",
                order_type="LIMIT",
                quantity=1.0,
            )

    def test_stop_requires_a_trigger(self) -> None:
        """A STOP_LOSS with no stop_price cannot be interpreted."""
        with pytest.raises(PydanticValidationError, match="require a stop_price"):
            SubmitPaperOrderRequest(
                account_id="00000000-0000-0000-0000-000000000000",
                symbol="BTCUSDT",
                side="SELL",
                order_type="STOP_LOSS",
                quantity=1.0,
            )


@pytest.mark.unit
class TestRestingOrders:
    """Placement, triggering, and cancellation."""

    @pytest.mark.asyncio
    async def test_limit_rests_without_touching_the_balance(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A resting order reserves nothing until it triggers."""
        client = MovablePriceClient(50_000.0)
        service = PaperTradingService(db_session, client=client)
        account = await service.create_account(
            test_user.id, CreatePaperAccountRequest(initial_balance=100_000.0)
        )

        order = await service.submit_order(
            test_user.id,
            SubmitPaperOrderRequest(
                account_id=account.id, symbol="BTCUSDT", side="BUY",
                order_type="LIMIT", quantity=0.5, price=48_000.0,
            ),
        )

        assert order.status == "PENDING"
        assert order.filled_quantity == 0.0
        assert account.current_balance == pytest.approx(100_000.0)

    @pytest.mark.asyncio
    async def test_limit_triggers_only_when_price_arrives(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A buy limit fills when the market falls to it, not before."""
        client = MovablePriceClient(50_000.0)
        service = PaperTradingService(db_session, client=client)
        account = await service.create_account(
            test_user.id, CreatePaperAccountRequest(initial_balance=100_000.0)
        )
        order = await service.submit_order(
            test_user.id,
            SubmitPaperOrderRequest(
                account_id=account.id, symbol="BTCUSDT", side="BUY",
                order_type="LIMIT", quantity=0.5, price=48_000.0,
            ),
        )

        assert (await service.process_pending_orders(account.id))["triggered"] == 0

        client.price = 47_900.0
        assert (await service.process_pending_orders(account.id))["triggered"] == 1

        await db_session.refresh(order)
        assert order.status == "FILLED"
        # A limit fills at its resting price, not at the lower market.
        assert order.filled_price == pytest.approx(48_000.0 * 1.0005)
        assert len(await service.get_positions(test_user.id, account.id)) == 1

    @pytest.mark.asyncio
    async def test_stop_loss_fills_at_market_not_at_its_trigger(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A stop fills at the price it triggered into.

        Filling at the trigger would model a guarantee the exchange does not
        give, and would understate slippage on exactly the trades that hurt.
        """
        client = MovablePriceClient(50_000.0)
        service = PaperTradingService(db_session, client=client)
        account = await service.create_account(
            test_user.id, CreatePaperAccountRequest(initial_balance=100_000.0)
        )
        await service.submit_order(
            test_user.id,
            SubmitPaperOrderRequest(
                account_id=account.id, symbol="BTCUSDT", side="BUY", quantity=0.5
            ),
        )
        stop = await service.submit_order(
            test_user.id,
            SubmitPaperOrderRequest(
                account_id=account.id, symbol="BTCUSDT", side="SELL",
                order_type="STOP_LOSS", quantity=0.5, stop_price=46_000.0,
            ),
        )

        assert (await service.process_pending_orders(account.id))["triggered"] == 0

        client.price = 45_000.0
        assert (await service.process_pending_orders(account.id))["triggered"] == 1

        await db_session.refresh(stop)
        assert stop.status == "FILLED"
        assert stop.filled_price == pytest.approx(45_000.0 * 0.9995)
        assert await service.get_positions(test_user.id, account.id) == []

    @pytest.mark.asyncio
    async def test_resting_sell_requires_an_existing_position(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """You cannot rest a sell for something you do not hold."""
        service = PaperTradingService(db_session, client=MovablePriceClient())
        account = await service.create_account(test_user.id, CreatePaperAccountRequest())

        with pytest.raises(ValidationError, match="position holds"):
            await service.submit_order(
                test_user.id,
                SubmitPaperOrderRequest(
                    account_id=account.id, symbol="BTCUSDT", side="SELL",
                    order_type="STOP_LOSS", quantity=1.0, stop_price=40_000.0,
                ),
            )

    @pytest.mark.asyncio
    async def test_unaffordable_order_is_rejected_at_trigger(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Balance is re-checked when the order fires, not only when placed.

        Nothing is reserved at placement, so the account may have been spent
        down in the meantime.
        """
        client = MovablePriceClient(50_000.0)
        service = PaperTradingService(db_session, client=client)
        account = await service.create_account(
            test_user.id, CreatePaperAccountRequest(initial_balance=30_000.0)
        )
        await service.submit_order(
            test_user.id,
            SubmitPaperOrderRequest(
                account_id=account.id, symbol="BTCUSDT", side="BUY",
                order_type="LIMIT", quantity=1.0, price=49_000.0,
            ),
        )
        # Spend the balance before the limit can fire.
        await service.submit_order(
            test_user.id,
            SubmitPaperOrderRequest(
                account_id=account.id, symbol="BTCUSDT", side="BUY", quantity=0.55
            ),
        )

        client.price = 48_000.0
        result = await service.process_pending_orders(account.id)
        assert result["rejected"] == 1
        assert result["triggered"] == 0

    @pytest.mark.asyncio
    async def test_cancel_removes_a_resting_order(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A pending order can be cancelled and stops being considered."""
        service = PaperTradingService(db_session, client=MovablePriceClient())
        account = await service.create_account(
            test_user.id, CreatePaperAccountRequest(initial_balance=100_000.0)
        )
        order = await service.submit_order(
            test_user.id,
            SubmitPaperOrderRequest(
                account_id=account.id, symbol="BTCUSDT", side="BUY",
                order_type="LIMIT", quantity=0.1, price=10_000.0,
            ),
        )

        cancelled = await service.cancel_order(test_user.id, order.id)
        assert cancelled.status == "CANCELLED"
        assert await service.get_pending_orders(test_user.id, account.id) == []

    @pytest.mark.asyncio
    async def test_cannot_cancel_a_filled_order(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A market order is already done and cannot be cancelled."""
        service = PaperTradingService(db_session, client=MovablePriceClient())
        account = await service.create_account(
            test_user.id, CreatePaperAccountRequest(initial_balance=100_000.0)
        )
        filled = await service.submit_order(
            test_user.id,
            SubmitPaperOrderRequest(
                account_id=account.id, symbol="BTCUSDT", side="BUY", quantity=0.1
            ),
        )

        with pytest.raises(ValidationError, match="cannot be cancelled"):
            await service.cancel_order(test_user.id, filled.id)

    @pytest.mark.asyncio
    async def test_another_user_cannot_cancel_your_order(
        self, db_session: AsyncSession, test_user: User, second_user: User
    ) -> None:
        """Ownership is enforced through the owning account."""
        from app.core.exceptions import AuthorizationError

        service = PaperTradingService(db_session, client=MovablePriceClient())
        account = await service.create_account(
            test_user.id, CreatePaperAccountRequest(initial_balance=100_000.0)
        )
        order = await service.submit_order(
            test_user.id,
            SubmitPaperOrderRequest(
                account_id=account.id, symbol="BTCUSDT", side="BUY",
                order_type="LIMIT", quantity=0.1, price=10_000.0,
            ),
        )

        with pytest.raises(AuthorizationError):
            await service.cancel_order(second_user.id, order.id)
