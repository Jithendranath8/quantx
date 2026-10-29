"""
QuantX — Unit Tests for the paper-trading risk gate.

Paper orders used to skip the risk engine entirely: no sizing limit, no
exposure or concurrency limit, and a tripped circuit breaker did not stop
them. Every BUY now passes RiskManager with the account's real book. These
tests run against the default limits (2% risk per trade, 50% exposure, five
concurrent positions).
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RiskLimitExceededError
from app.models.user import User
from app.schemas.paper_trading import CreatePaperAccountRequest, SubmitPaperOrderRequest
from app.services.paper_trading_service import PaperTradingService
from app.services.risk_state_service import RiskStateService


class FixedPriceClient:
    """Every symbol trades at one controllable price."""

    testnet = True

    def __init__(self, price: float = 50_000.0) -> None:
        self.price = price

    async def get_price(self, symbol: str) -> float:
        return self.price


async def funded(session: AsyncSession, user: User, client: FixedPriceClient) -> tuple[PaperTradingService, object]:
    service = PaperTradingService(session, client=client)
    account = await service.create_account(user.id, CreatePaperAccountRequest(initial_balance=100_000.0))
    return service, account


def buy(account: object, quantity: float, symbol: str = "BTCUSDT", **extra: object) -> SubmitPaperOrderRequest:
    return SubmitPaperOrderRequest(account_id=account.id, symbol=symbol, side="BUY", quantity=quantity, **extra)  # type: ignore[attr-defined]


@pytest.mark.unit
class TestPaperRiskGate:
    @pytest.mark.asyncio
    async def test_oversized_order_without_a_stop_is_refused(self, db_session: AsyncSession, test_user: User) -> None:
        """Without a stop the engine allows 5x the 2% risk budget: $10k on $100k."""
        service, account = await funded(db_session, test_user, FixedPriceClient())

        with pytest.raises(RiskLimitExceededError, match=r"risk-per-trade limit of \$10,000\.00 without a stop loss"):
            await service.submit_order(test_user.id, buy(account, 0.3))  # $15k

        order = await service.submit_order(test_user.id, buy(account, 0.1))  # $5k
        assert order.status == "FILLED"

    @pytest.mark.asyncio
    async def test_a_tight_stop_permits_a_larger_position(self, db_session: AsyncSession, test_user: User) -> None:
        """A 2% stop risks $2k on a $100k position, so $25k is well inside the budget."""
        service, account = await funded(db_session, test_user, FixedPriceClient())

        order = await service.submit_order(test_user.id, buy(account, 0.5, stop_loss=49_000.0))
        assert order.status == "FILLED"

    @pytest.mark.asyncio
    async def test_exposure_limit_counts_positions_already_open(self, db_session: AsyncSession, test_user: User) -> None:
        """Each order fits on its own; together they would exceed 50% of equity."""
        service, account = await funded(db_session, test_user, FixedPriceClient())
        await service.submit_order(test_user.id, buy(account, 0.6, stop_loss=49_000.0))  # $30k

        with pytest.raises(RiskLimitExceededError, match="portfolio exposure"):
            await service.submit_order(test_user.id, buy(account, 0.5, symbol="ETHUSDT", stop_loss=49_000.0))

    @pytest.mark.asyncio
    async def test_concurrent_position_limit(self, db_session: AsyncSession, test_user: User) -> None:
        """A sixth symbol is refused; adding to an existing position is not a new one."""
        service, account = await funded(db_session, test_user, FixedPriceClient(price=100.0))
        for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
            await service.submit_order(test_user.id, buy(account, 1, symbol=symbol))

        with pytest.raises(RiskLimitExceededError, match="Active position limit"):
            await service.submit_order(test_user.id, buy(account, 1, symbol="ADAUSDT"))

        order = await service.submit_order(test_user.id, buy(account, 1, symbol="BTCUSDT"))
        assert order.status == "FILLED"

    @pytest.mark.asyncio
    async def test_halt_blocks_buys_but_still_lets_you_exit(self, db_session: AsyncSession, test_user: User) -> None:
        """A tripped breaker refuses new risk; it must never trap an open position."""
        service, account = await funded(db_session, test_user, FixedPriceClient())
        await service.submit_order(test_user.id, buy(account, 0.1))
        await RiskStateService(db_session).set_circuit_breaker(test_user.id, True, "MANUAL_TEST_HALT")
        await db_session.commit()

        with pytest.raises(RiskLimitExceededError, match="Circuit breaker"):
            await service.submit_order(test_user.id, buy(account, 0.01))

        exit_order = await service.submit_order(
            test_user.id,
            SubmitPaperOrderRequest(account_id=account.id, symbol="BTCUSDT", side="SELL", quantity=0.1),
        )
        assert exit_order.status == "FILLED"

    @pytest.mark.asyncio
    async def test_resting_buy_is_rechecked_when_it_triggers(self, db_session: AsyncSession, test_user: User) -> None:
        """A limit placed before a halt is refused at trigger time, not filled."""
        client = FixedPriceClient()
        service, account = await funded(db_session, test_user, client)
        resting = await service.submit_order(
            test_user.id, buy(account, 0.1, order_type="LIMIT", price=49_000.0)
        )
        assert resting.status == "PENDING"

        await RiskStateService(db_session).set_circuit_breaker(test_user.id, True, "MANUAL_TEST_HALT")
        await db_session.commit()
        client.price = 48_000.0

        counts = await service.process_pending_orders(account.id)  # type: ignore[attr-defined]
        assert counts["rejected"] == 1
        assert counts["triggered"] == 0
        await db_session.refresh(resting)
        assert resting.status == "REJECTED"

    @pytest.mark.asyncio
    async def test_daily_loss_limit_is_per_account_and_resets_at_utc_midnight(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A losing day blocks that account's buys without halting anything else."""
        from datetime import UTC, datetime, timedelta

        from sqlalchemy import update

        from app.models.paper_trading import PaperOrder

        client = FixedPriceClient()
        service, account = await funded(db_session, test_user, client)
        await service.submit_order(test_user.id, buy(account, 0.9, stop_loss=49_000.0))  # ~$45k
        client.price = 44_000.0
        losing_exit = await service.submit_order(
            test_user.id,
            SubmitPaperOrderRequest(account_id=account.id, symbol="BTCUSDT", side="SELL", quantity=0.9),
        )
        assert losing_exit.realized_pnl is not None and losing_exit.realized_pnl < -5_000  # > 5% of equity

        with pytest.raises(RiskLimitExceededError, match="Max daily loss"):
            await service.submit_order(test_user.id, buy(account, 0.01))

        # The shared breaker (which would also halt live trading) is untouched,
        # and another account of the same user can still trade.
        assert await RiskStateService(db_session).is_halted(test_user.id) is False
        other = await service.create_account(test_user.id, CreatePaperAccountRequest(initial_balance=100_000.0))
        assert (await service.submit_order(test_user.id, buy(other, 0.01))).status == "FILLED"

        # Yesterday's losses do not count today.
        await db_session.execute(
            update(PaperOrder)
            .where(PaperOrder.id == losing_exit.id)
            .values(filled_at=datetime.now(UTC) - timedelta(days=1))
        )
        await db_session.commit()
        assert (await service.submit_order(test_user.id, buy(account, 0.01))).status == "FILLED"

    @pytest.mark.asyncio
    async def test_cooldown_blocks_rebuying_a_symbol_just_closed_at_a_loss(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        from datetime import UTC, datetime, timedelta

        from sqlalchemy import update

        from app.models.paper_trading import PaperOrder

        client = FixedPriceClient()
        service, account = await funded(db_session, test_user, client)
        await service.submit_order(test_user.id, buy(account, 0.1))
        client.price = 49_000.0
        exit_order = await service.submit_order(
            test_user.id,
            SubmitPaperOrderRequest(account_id=account.id, symbol="BTCUSDT", side="SELL", quantity=0.1),
        )
        assert exit_order.realized_pnl is not None and exit_order.realized_pnl < 0

        with pytest.raises(RiskLimitExceededError, match="Cooldown"):
            await service.submit_order(test_user.id, buy(account, 0.01))
        # Other symbols are unaffected.
        assert (await service.submit_order(test_user.id, buy(account, 0.01, symbol="ETHUSDT"))).status == "FILLED"

        await db_session.execute(
            update(PaperOrder)
            .where(PaperOrder.id == exit_order.id)
            .values(filled_at=datetime.now(UTC) - timedelta(minutes=20))
        )
        await db_session.commit()
        assert (await service.submit_order(test_user.id, buy(account, 0.01))).status == "FILLED"

    @pytest.mark.asyncio
    async def test_exposure_is_valued_at_the_current_price_not_the_last_fill(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A position that doubled is twice the exposure, even before mark-to-market."""
        client = FixedPriceClient()
        service, account = await funded(db_session, test_user, client)
        await service.submit_order(test_user.id, buy(account, 0.4, stop_loss=49_000.0))  # $20k at fill
        client.price = 100_000.0  # now worth $40k; equity ~$120k, so the cap is ~$60k

        with pytest.raises(RiskLimitExceededError, match="portfolio exposure"):
            await service.submit_order(test_user.id, buy(account, 0.25, stop_loss=98_000.0))  # +$25k
