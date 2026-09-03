"""
QuantX — Unit Tests for Live Trading, the Kill Switch, and persisted risk state.

The exchange is stubbed. These tests assert on what the service does with the
exchange's answers, including the failure paths, rather than on a hardcoded
"FILLED" that the previous implementation returned unconditionally.
"""

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConfigurationError, RiskLimitExceededError
from app.models.live_trading import LiveOrder
from app.models.user import User
from app.schemas.live_trading import LiveOrderRequest
from app.services.kill_switch import KillSwitchService
from app.services.live_trading_service import LiveTradingService
from app.services.risk_state_service import RiskStateService


class StubBinanceClient:
    """Records calls and returns scripted exchange responses."""

    def __init__(self, **overrides: Any) -> None:
        self.testnet = True
        self.placed: list[dict[str, Any]] = []
        self.cancelled: list[tuple[str, Any]] = []
        self._overrides = overrides
        self.open_orders: list[dict[str, Any]] = overrides.get("open_orders", [])
        self.order_status = overrides.get("order_status", "CANCELED")
        self.cancel_error: Exception | None = overrides.get("cancel_error")

    async def get_price(self, symbol: str) -> float:
        return 50_000.0

    async def get_balances(self) -> dict[str, float]:
        return {"USDT": self._overrides.get("balance", 100_000.0)}

    async def get_exchange_info(self) -> dict[str, Any]:
        return {"symbols": [{"symbol": "BTCUSDT", "quoteAsset": "USDT"}]}

    async def place_order(self, **kwargs: Any) -> dict[str, Any]:
        if self._overrides.get("place_error"):
            raise self._overrides["place_error"]
        self.placed.append(kwargs)
        return {
            "orderId": 987654,
            "status": "FILLED",
            "executedQty": str(kwargs["quantity"]),
            "cummulativeQuoteQty": str(kwargs["quantity"] * 50_000.0),
            "transactTime": 1767225600000,
            "fills": [
                {
                    "price": "50000.0",
                    "qty": str(kwargs["quantity"]),
                    "commission": "0.5",
                    "commissionAsset": "USDT",
                }
            ],
        }

    async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        return self.open_orders

    async def cancel_order(self, symbol: str, order_id: Any) -> dict[str, Any]:
        if self.cancel_error:
            raise self.cancel_error
        self.cancelled.append((symbol, order_id))
        return {"status": "CANCELED"}

    async def get_order(self, symbol: str, order_id: Any) -> dict[str, Any]:
        return {"status": self.order_status}


def order_request(**kwargs: Any) -> LiveOrderRequest:
    """Build a live order request with sensible defaults."""
    return LiveOrderRequest(
        **{
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.1,
            "price": 50_000.0,
            **kwargs,
        }
    )


@pytest.mark.unit
class TestLiveTradingService:
    """Order execution against a stubbed exchange."""

    @pytest.mark.asyncio
    async def test_order_persists_and_records_exchange_response(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A successful order stores the exchange's own ids and fills."""
        client = StubBinanceClient()
        service = LiveTradingService(db_session, client=client)

        res = await service.execute_live_order(test_user.id, order_request())

        assert res.status == "FILLED"
        assert res.order_id == "987654"
        assert len(client.placed) == 1
        # The client_order_id we generated was sent for idempotency.
        assert client.placed[0]["client_order_id"].startswith("qx")

        stored = (
            await db_session.execute(select(LiveOrder).where(LiveOrder.user_id == test_user.id))
        ).scalar_one()
        assert stored.exchange_order_id == "987654"
        assert stored.filled_quantity == pytest.approx(0.1)
        assert stored.commission == pytest.approx(0.5)
        assert stored.is_testnet is True

    @pytest.mark.asyncio
    async def test_risk_rejection_blocks_the_exchange_call(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Excessive leverage is rejected before anything reaches the exchange."""
        client = StubBinanceClient()
        service = LiveTradingService(db_session, client=client)

        with pytest.raises(RiskLimitExceededError):
            await service.execute_live_order(test_user.id, order_request(leverage=20))

        assert client.placed == []

    @pytest.mark.asyncio
    async def test_active_circuit_breaker_blocks_orders(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A persisted halt stops new orders in any process."""
        await RiskStateService(db_session).set_circuit_breaker(test_user.id, True, "test halt")
        await db_session.commit()

        client = StubBinanceClient()
        with pytest.raises(RiskLimitExceededError):
            await LiveTradingService(db_session, client=client).execute_live_order(
                test_user.id, order_request()
            )
        assert client.placed == []

    @pytest.mark.asyncio
    async def test_halt_is_checked_before_any_exchange_call(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A halted account is told it is halted, not something else.

        Resolving the price and balance before the halt check meant a missing
        credentials error masked the real reason, and made exchange requests on
        behalf of an account forbidden from trading.
        """
        await RiskStateService(db_session).set_circuit_breaker(test_user.id, True, "test halt")
        await db_session.commit()

        class ExplodingClient(StubBinanceClient):
            async def get_price(self, symbol: str) -> float:
                raise AssertionError("must not contact the exchange while halted")

            async def get_balances(self) -> dict[str, Any]:
                raise AssertionError("must not contact the exchange while halted")

        service = LiveTradingService(db_session, client=ExplodingClient())
        with pytest.raises(RiskLimitExceededError, match="circuit breaker is ACTIVE"):
            await service.execute_live_order(test_user.id, order_request(price=None))

    @pytest.mark.asyncio
    async def test_indeterminate_submit_is_flagged_for_reconciliation(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A network failure leaves a durable record, not a silent gap.

        The order may or may not exist on the exchange, so it is marked for
        reconciliation rather than reported as a clean failure.
        """
        client = StubBinanceClient(place_error=TimeoutError("connection reset"))
        service = LiveTradingService(db_session, client=client)

        with pytest.raises(TimeoutError):
            await service.execute_live_order(test_user.id, order_request())

        stored = (
            await db_session.execute(select(LiveOrder).where(LiveOrder.user_id == test_user.id))
        ).scalar_one()
        assert stored.status == "UNKNOWN_NEEDS_RECONCILIATION"
        assert stored.client_order_id

    @pytest.mark.asyncio
    async def test_configuration_error_marks_order_rejected(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A refused mainnet order is recorded as REJECTED with the reason."""
        client = StubBinanceClient(place_error=ConfigurationError("mainnet not enabled"))
        service = LiveTradingService(db_session, client=client)

        with pytest.raises(ConfigurationError):
            await service.execute_live_order(test_user.id, order_request())

        stored = (
            await db_session.execute(select(LiveOrder).where(LiveOrder.user_id == test_user.id))
        ).scalar_one()
        assert stored.status == "REJECTED"
        assert "mainnet" in stored.rejection_reason


@pytest.mark.unit
class TestKillSwitch:
    """Emergency halt behaviour."""

    @pytest.mark.asyncio
    async def test_kill_switch_persists_halt(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Activation writes the breaker to the database, not to an object."""
        res = await KillSwitchService(db_session, client=StubBinanceClient()).activate_kill_switch(
            test_user.id
        )
        assert res["status"] == "HALTED"
        assert res["circuit_breaker_active"] is True
        assert await RiskStateService(db_session).is_halted(test_user.id) is True

    @pytest.mark.asyncio
    async def test_kill_switch_cancels_and_verifies_exchange_orders(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Open exchange orders are cancelled and confirmed terminal."""
        db_session.add(
            LiveOrder(
                user_id=test_user.id,
                client_order_id=f"qx{uuid.uuid4().hex[:20]}",
                exchange_order_id="111",
                symbol="BTCUSDT",
                side="BUY",
                order_type="LIMIT",
                quantity=1.0,
                status="NEW",
            )
        )
        await db_session.commit()

        client = StubBinanceClient(
            open_orders=[{"orderId": 111, "symbol": "BTCUSDT"}], order_status="CANCELED"
        )
        res = await KillSwitchService(db_session, client=client).activate_kill_switch(test_user.id)

        assert client.cancelled == [("BTCUSDT", 111)]
        assert res["binance_orders_cancelled"] == 1
        assert res["fully_successful"] is True

    @pytest.mark.asyncio
    async def test_failed_cancellation_is_reported_not_swallowed(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A cancellation failure surfaces in the result.

        The old implementation caught the exception, logged a warning and still
        returned a success payload, so an operator believed they were flat when
        their orders were still live.
        """
        db_session.add(
            LiveOrder(
                user_id=test_user.id,
                client_order_id=f"qx{uuid.uuid4().hex[:20]}",
                exchange_order_id="222",
                symbol="BTCUSDT",
                side="BUY",
                order_type="LIMIT",
                quantity=1.0,
                status="NEW",
            )
        )
        await db_session.commit()

        client = StubBinanceClient(
            open_orders=[{"orderId": 222, "symbol": "BTCUSDT"}],
            cancel_error=RuntimeError("exchange unreachable"),
        )
        res = await KillSwitchService(db_session, client=client).activate_kill_switch(test_user.id)

        assert res["fully_successful"] is False
        assert res["binance_cancellations_failed"] == 1
        assert any("exchange unreachable" in e for e in res["errors"])
        # Trading is still halted even though cancellation failed.
        assert res["circuit_breaker_active"] is True

    @pytest.mark.asyncio
    async def test_unverified_cancellation_counts_as_failure(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """An order that does not reach a terminal state is not counted cancelled."""
        db_session.add(
            LiveOrder(
                user_id=test_user.id,
                client_order_id=f"qx{uuid.uuid4().hex[:20]}",
                exchange_order_id="333",
                symbol="BTCUSDT",
                side="BUY",
                order_type="LIMIT",
                quantity=1.0,
                status="NEW",
            )
        )
        await db_session.commit()

        client = StubBinanceClient(
            open_orders=[{"orderId": 333, "symbol": "BTCUSDT"}], order_status="NEW"
        )
        res = await KillSwitchService(db_session, client=client).activate_kill_switch(test_user.id)

        assert res["binance_orders_cancelled"] == 0
        assert res["binance_cancellations_failed"] == 1
        assert res["fully_successful"] is False

    @pytest.mark.asyncio
    async def test_deactivate_releases_the_halt(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """The breaker can be released again."""
        service = KillSwitchService(db_session, client=StubBinanceClient())
        await service.activate_kill_switch(test_user.id)
        res = await service.deactivate_kill_switch(test_user.id)

        assert res["circuit_breaker_active"] is False
        assert await RiskStateService(db_session).is_halted(test_user.id) is False
