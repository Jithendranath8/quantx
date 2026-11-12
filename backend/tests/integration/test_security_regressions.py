"""
QuantX — Regression tests for the 2026-11-12 security audit.

Each test reproduces one confirmed finding and asserts the fixed behaviour. The
finding number in each docstring refers to docs/SECURITY_AUDIT.md. A test here
that starts failing means a security fix has been undone.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from jose import jwt
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import BinanceRejectedError, RiskLimitExceededError
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.models.live_trading import LiveOrder
from app.models.paper_trading import PaperOrder, PaperPosition
from app.models.user import User
from app.repositories.user_repository import RefreshTokenRepository
from app.schemas.live_trading import LiveOrderRequest
from app.schemas.paper_trading import CreatePaperAccountRequest, SubmitPaperOrderRequest
from app.services.kill_switch import KillSwitchService
from app.services.live_trading_service import LiveTradingService
from app.services.paper_trading_service import PaperTradingService
from app.services.reconciliation_service import OrderReconciliationService
from tests.conftest import test_session_factory
from tests.unit.test_live_trading import StubBinanceClient, order_request

REGISTER = {
    "email": "session.user@quantx.io",
    "username": "sessionuser",
    "password": "StrongP@ss1",
    "full_name": "Session User",
}


def _working_order(user: User, **kwargs: Any) -> LiveOrder:
    """A live order resting on the exchange."""
    fields: dict[str, Any] = {
        "user_id": user.id,
        "client_order_id": f"qx{uuid.uuid4().hex[:30]}",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": 1.0,
        "price": 50_000.0,
        "status": "NEW",
        "is_testnet": True,
    }
    fields.update(kwargs)
    return LiveOrder(**fields)


# ── Finding 1: live trading needs a permission ───────────────────────


@pytest.mark.integration
class TestLiveTradingPermission:
    @pytest.mark.asyncio
    async def test_a_registered_user_cannot_place_live_orders(
        self, client: AsyncClient, auth_headers: dict, stub_binance: Any
    ) -> None:
        """Finding 1: sign-up alone must not reach the operator's exchange account."""
        response = await client.post(
            "/api/v1/live/orders",
            headers=auth_headers,
            json={"symbol": "BTCUSDT", "side": "BUY", "order_type": "LIMIT", "quantity": 0.01, "price": 50000.0},
        )
        assert response.status_code == 403
        assert "Live trading is not enabled" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_registration_cannot_grant_the_permission(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Finding 1: a caller cannot set the flag on their own account."""
        response = await client.post("/api/v1/auth/register", json={**REGISTER, "can_trade_live": True})
        assert response.status_code == 201
        user = await db_session.get(User, uuid.UUID(response.json()["user"]["id"]))
        assert user is not None and user.can_trade_live is False

    @pytest.mark.asyncio
    async def test_a_sell_cannot_exceed_what_the_user_bought(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Finding 1: on the shared account a SELL is bounded by the caller's own book."""
        client = StubBinanceClient()
        with pytest.raises(RiskLimitExceededError, match="exceeds"):
            await LiveTradingService(db_session, client=client).execute_live_order(
                test_user.id, order_request(side="SELL", quantity=40.0)
            )
        assert client.placed == []


# ── Finding 2: kill switch scope ─────────────────────────────────────


@pytest.mark.integration
class TestKillSwitchScope:
    @pytest.mark.asyncio
    async def test_kill_switch_leaves_other_peoples_orders_alone(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Finding 2: only the caller's own exchange orders are cancelled."""
        mine = _working_order(test_user, exchange_order_id="7004")
        db_session.add(mine)
        await db_session.commit()

        client = StubBinanceClient(
            open_orders=[
                {"orderId": 7001, "clientOrderId": "another-users-order", "symbol": "BTCUSDT"},
                {"orderId": 7003, "clientOrderId": "placed-outside-quantx", "symbol": "BTCUSDT"},
                {"orderId": 7004, "clientOrderId": mine.client_order_id, "symbol": "BTCUSDT"},
            ]
        )
        result = await KillSwitchService(db_session, client=client).activate_kill_switch(test_user.id)

        assert client.cancelled == [("BTCUSDT", 7004)]
        assert result["binance_orders_cancelled"] == 1
        assert result["fully_successful"] is True


# ── Finding 3: the risk price is not the caller's to choose ──────────


@pytest.mark.integration
class TestRiskReferencePrice:
    def test_a_market_order_takes_no_price(self) -> None:
        """Finding 3: the field that let a caller pick the sizing price is refused."""
        with pytest.raises(PydanticValidationError, match="MARKET orders take no price"):
            LiveOrderRequest(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=9.0, price=1.0)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0.0, -1.0])
    def test_prices_must_be_positive_and_finite(self, bad: float) -> None:
        with pytest.raises(PydanticValidationError):
            LiveOrderRequest(symbol="BTCUSDT", side="BUY", order_type="LIMIT", quantity=1.0, price=bad)

    @pytest.mark.parametrize("symbol", ["A" * 200_000, "BTC/USDT", "BTC USDT", "*", ""])
    def test_symbols_have_a_bounded_shape(self, symbol: str) -> None:
        """An arbitrary string must not become a metric label or a log line."""
        with pytest.raises(PydanticValidationError):
            LiveOrderRequest(symbol=symbol, side="BUY", order_type="LIMIT", quantity=1.0, price=1.0)

    @pytest.mark.asyncio
    async def test_a_market_buy_is_sized_at_the_venue_price(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Finding 3: 9 BTC at the venue's 50,000 breaches the limits whatever the request says."""
        client = StubBinanceClient(balance=1_000_000.0)
        with pytest.raises(RiskLimitExceededError):
            await LiveTradingService(db_session, client=client).execute_live_order(
                test_user.id, order_request(order_type="MARKET", price=None, quantity=9.0)
            )
        assert client.placed == []


# ── Finding 4: working orders count toward the limits ────────────────


@pytest.mark.integration
class TestWorkingOrdersCount:
    @pytest.mark.asyncio
    async def test_resting_buys_are_exposure(self, db_session: AsyncSession, test_user: User) -> None:
        """Finding 4: a ladder of resting limit buys cannot exceed the exposure cap."""
        for _ in range(12):
            db_session.add(_working_order(test_user))  # 12 x $50k resting = $600k locked
        await db_session.commit()
        # $400k free + $600k locked in resting orders = $1M equity, 60% committed.
        client = StubBinanceClient(balance=400_000.0)

        with pytest.raises(RiskLimitExceededError, match=r"portfolio exposure|concurrent"):
            await LiveTradingService(db_session, client=client).execute_live_order(
                test_user.id, order_request(quantity=0.1, stop_price=49_000.0)
            )
        assert client.placed == []

    @pytest.mark.asyncio
    async def test_reconciliation_records_the_fill_price(self, db_session: AsyncSession, test_user: User) -> None:
        """Finding 4: an order that fills after placement becomes a position in the book."""
        order = _working_order(test_user, exchange_order_id="555")
        db_session.add(order)
        await db_session.commit()

        class FilledLater(StubBinanceClient):
            async def get_order(self, symbol: str, order_id: Any = None, *, client_order_id: str | None = None) -> dict[str, Any]:
                return {"orderId": 555, "status": "FILLED", "executedQty": "1.0", "cummulativeQuoteQty": "50000.0"}

        client = FilledLater()
        await OrderReconciliationService(db_session, client=client).reconcile_orders(test_user.id)  # type: ignore[arg-type]

        assert order.status == "FILLED"
        assert order.filled_price == pytest.approx(50_000.0)
        book = await LiveTradingService(db_session, client=client)._book(test_user.id)  # type: ignore[arg-type]
        assert book.holdings["BTCUSDT"].quantity == pytest.approx(1.0)


# ── Indeterminate submits (audit coverage gap 4) ─────────────────────


@pytest.mark.integration
class TestOrderOutcome:
    @pytest.mark.asyncio
    async def test_an_exchange_rejection_is_final(self, db_session: AsyncSession, test_user: User) -> None:
        """A 4xx from the exchange is REJECTED, not left to reconcile forever."""
        client = StubBinanceClient(
            place_error=BinanceRejectedError("POST /api/v3/order rejected", {"status": 400, "code": -2010})
        )
        with pytest.raises(BinanceRejectedError):
            await LiveTradingService(db_session, client=client).execute_live_order(test_user.id, order_request())
        order = (await db_session.execute(select(LiveOrder))).scalar_one()
        assert order.status == "REJECTED"

    @pytest.mark.asyncio
    async def test_a_lost_response_is_resolved_by_client_id(self, db_session: AsyncSession, test_user: User) -> None:
        """An order with no exchange id is looked up by its client order id."""
        order = _working_order(test_user, status="UNKNOWN_NEEDS_RECONCILIATION")
        db_session.add(order)
        await db_session.commit()
        asked: list[str | None] = []

        class Landed(StubBinanceClient):
            async def get_order(self, symbol: str, order_id: Any = None, *, client_order_id: str | None = None) -> dict[str, Any]:
                asked.append(client_order_id)
                return {"orderId": 901, "status": "NEW", "executedQty": "0"}

        report = await OrderReconciliationService(db_session, client=Landed()).reconcile_orders(test_user.id)  # type: ignore[arg-type]

        assert asked == [order.client_order_id]
        assert order.status == "NEW" and order.exchange_order_id == "901"
        assert report["repaired_count"] == 1

    @pytest.mark.asyncio
    async def test_cancel_asks_the_exchange_before_declaring_an_order_gone(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A row with no exchange id may be working; cancelling it must reach the exchange."""
        order = _working_order(test_user, status="UNKNOWN_NEEDS_RECONCILIATION")
        db_session.add(order)
        await db_session.commit()
        cancelled: list[str | None] = []

        class Working(StubBinanceClient):
            async def get_order(self, symbol: str, order_id: Any = None, *, client_order_id: str | None = None) -> dict[str, Any]:
                return {"orderId": 902, "status": "NEW", "executedQty": "0"}

            async def cancel_order(self, symbol: str, order_id: Any = None, *, client_order_id: str | None = None) -> dict[str, Any]:
                cancelled.append(client_order_id)
                return {"status": "CANCELED"}

        result = await LiveTradingService(db_session, client=Working()).cancel_order(test_user.id, order.id)  # type: ignore[arg-type]

        assert cancelled == [order.client_order_id]
        assert result.status == "CANCELED"


# ── Finding 10: the paper fill sweep ─────────────────────────────────


class _Market:
    """A market whose price the test controls."""

    testnet = True

    def __init__(self, price: float) -> None:
        self.price = price

    async def get_price(self, symbol: str) -> float:
        return self.price


@pytest.mark.integration
class TestPaperSweep:
    @pytest.mark.asyncio
    async def test_fills_in_one_sweep_see_each_other(self, db_session: AsyncSession, test_user: User) -> None:
        """Finding 10: two buys filled in one sweep make one position and respect the cap."""
        market = _Market(60_000.0)
        service = PaperTradingService(db_session, client=market)  # type: ignore[arg-type]
        account = await service.create_account(test_user.id, CreatePaperAccountRequest(initial_balance=100_000.0))
        for _ in range(2):  # two $30k buys: each passes alone, together they are 60% against a 50% cap
            await service.submit_order(
                test_user.id,
                SubmitPaperOrderRequest(
                    account_id=account.id,
                    symbol="BTCUSDT",
                    side="BUY",
                    order_type="LIMIT",
                    quantity=0.6,
                    price=50_000.0,
                    stop_loss=49_900.0,
                ),
            )

        market.price = 49_990.0  # both trigger in the same sweep
        result = await service.process_pending_orders()

        open_rows = await db_session.scalar(
            select(func.count()).select_from(PaperPosition).where(
                PaperPosition.account_id == account.id, PaperPosition.status == "OPEN"
            )
        )
        assert open_rows == 1
        assert result["triggered"] == 1 and result["rejected"] == 1

    @pytest.mark.asyncio
    async def test_one_bad_order_does_not_stop_the_sweep(
        self, db_session: AsyncSession, test_user: User, second_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Finding 10: an order that raises is skipped; everyone else's still fill."""
        market = _Market(60_000.0)
        service = PaperTradingService(db_session, client=market)  # type: ignore[arg-type]
        orders = {}
        for user in (test_user, second_user):
            account = await service.create_account(user.id, CreatePaperAccountRequest(initial_balance=100_000.0))
            orders[user.id] = await service.submit_order(
                user.id,
                SubmitPaperOrderRequest(
                    account_id=account.id,
                    symbol="BTCUSDT",
                    side="BUY",
                    order_type="LIMIT",
                    quantity=0.1,
                    price=50_000.0,
                    stop_loss=49_900.0,
                ),
            )
        poisoned = orders[test_user.id].id
        real_fill = PaperTradingService._fill_resting_order

        async def fill(self: PaperTradingService, order: PaperOrder, price: float) -> bool:
            if order.id == poisoned:
                raise RuntimeError("corrupt row")
            return await real_fill(self, order, price)

        monkeypatch.setattr(PaperTradingService, "_fill_resting_order", fill)
        market.price = 49_990.0
        result = await service.process_pending_orders()

        assert result["failed"] == 1 and result["triggered"] == 1
        victim = await db_session.get(PaperOrder, orders[second_user.id].id)
        assert victim is not None and victim.status == "FILLED"

    @pytest.mark.asyncio
    async def test_resting_orders_are_capped_per_account(self, db_session: AsyncSession, test_user: User) -> None:
        """One account cannot grow the shared sweep's backlog without limit."""
        from app.core.exceptions import ValidationError
        from app.services import paper_trading_service as module

        service = PaperTradingService(db_session, client=_Market(60_000.0))  # type: ignore[arg-type]
        account = await service.create_account(test_user.id, CreatePaperAccountRequest(initial_balance=1_000_000.0))
        request = SubmitPaperOrderRequest(
            account_id=account.id, symbol="BTCUSDT", side="BUY", order_type="LIMIT",
            quantity=0.001, price=50_000.0, stop_loss=49_900.0,
        )
        for _ in range(module.MAX_PENDING_ORDERS_PER_ACCOUNT):
            await service.submit_order(test_user.id, request)
        with pytest.raises(ValidationError, match="at most"):
            await service.submit_order(test_user.id, request)


# ── Findings 11-13: sessions ─────────────────────────────────────────


@pytest.mark.integration
class TestSessions:
    @pytest.mark.asyncio
    async def test_sign_out_everywhere_ends_access_tokens(self, client: AsyncClient) -> None:
        """Finding 11: the access token stops working at once, not 30 minutes later."""
        tokens = (await client.post("/api/v1/auth/register", json=REGISTER)).json()["tokens"]
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200

        assert (await client.post("/api/v1/auth/logout-all", headers=headers)).status_code == 200

        assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
        assert (await client.get("/api/v1/risk/config", headers=headers)).status_code == 401

    @pytest.mark.asyncio
    async def test_logout_ends_that_sessions_access_token(self, client: AsyncClient) -> None:
        """Finding 11: logging out one session ends its access token."""
        tokens = (await client.post("/api/v1/auth/register", json=REGISTER)).json()["tokens"]
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        await client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})

        assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401

    @pytest.mark.asyncio
    async def test_logout_works_without_a_valid_access_token(self, client: AsyncClient) -> None:
        """Finding 12: an expired access token must not keep the refresh token alive."""
        tokens = (await client.post("/api/v1/auth/register", json=REGISTER)).json()["tokens"]

        response = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers={"Authorization": "Bearer expired-or-garbage"},
        )
        assert response.status_code == 200

        refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert refreshed.status_code == 401

    @pytest.mark.asyncio
    async def test_a_refreshed_session_stays_signed_in(self, client: AsyncClient) -> None:
        """Rotation continues the session; it does not sign the user out."""
        tokens = (await client.post("/api/v1/auth/register", json=REGISTER)).json()["tokens"]
        refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert refreshed.status_code == 200
        for token in (tokens["access_token"], refreshed.json()["access_token"]):
            me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert me.status_code == 200

    @pytest.mark.asyncio
    async def test_a_deactivated_account_is_refused_everywhere(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict
    ) -> None:
        """Finding 11: routes that only needed the user id skipped the active check."""
        test_user.is_active = False
        await db_session.commit()
        for method, path in (("GET", "/api/v1/auth/me"), ("POST", "/api/v1/auth/logout-all")):
            response = await client.request(method, path, headers=auth_headers)
            assert response.status_code == 403, path

    @pytest.mark.asyncio
    async def test_a_token_with_no_expiry_is_refused(self, client: AsyncClient, test_user: User) -> None:
        """A correctly signed token must still carry exp, iat and sub."""
        settings = get_settings()
        forever = jwt.encode(
            {"sub": str(test_user.id), "type": "access", "iat": datetime.now(UTC)},
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forever}"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_a_refresh_token_is_redeemed_exactly_once(self) -> None:
        """Finding 13: two overlapping redemptions of one token; one wins."""
        user_id = uuid.uuid4()
        token = create_refresh_token(str(user_id))
        async with test_session_factory() as setup:
            setup.add(
                User(
                    id=user_id,
                    email=f"race-{user_id.hex[:8]}@quantx.io",
                    username=f"race{user_id.hex[:8]}",
                    hashed_password=hash_password("RaceP@ss123"),
                )
            )
            await setup.flush()
            await RefreshTokenRepository(setup).create(user_id, token)
            await setup.commit()

        async def redeem() -> bool:
            async with test_session_factory() as session:
                consumed = await RefreshTokenRepository(session).consume(token)
                await asyncio.sleep(0.05)  # hold the transaction open across the other attempt
                await session.commit()
                return consumed is not None

        try:
            outcomes = await asyncio.gather(*(redeem() for _ in range(8)))
        finally:
            async with test_session_factory() as cleanup:
                user = await cleanup.get(User, user_id)
                if user is not None:
                    await cleanup.delete(user)
                    await cleanup.commit()

        assert sorted(outcomes) == [False] * 7 + [True]

    @pytest.mark.asyncio
    async def test_reusing_a_refresh_token_ends_every_session(self, client: AsyncClient) -> None:
        """Reuse detection still fires, and now also ends the access tokens."""
        tokens = (await client.post("/api/v1/auth/register", json=REGISTER)).json()["tokens"]
        first = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert first.status_code == 200

        replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert replay.status_code == 401

        headers = {"Authorization": f"Bearer {first.json()['access_token']}"}
        assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


def test_legacy_tokens_without_a_session_still_work_until_they_expire() -> None:
    """Tokens issued before sessions were tracked carry no sid and simply age out."""
    token = create_access_token(subject=str(uuid.uuid4()))
    claims = jwt.get_unverified_claims(token)
    assert "sid" not in claims
    assert datetime.fromtimestamp(claims["exp"], tz=UTC) - datetime.now(UTC) <= timedelta(
        minutes=get_settings().jwt_access_token_expire_minutes
    )


# ── Finding 9: Monte Carlo memory ────────────────────────────────────


class TestMonteCarloBudget:
    def test_work_is_capped_by_simulations_times_trades(self) -> None:
        """Finding 9: many trades reduce the simulation count instead of allocating gigabytes."""
        from app.engines.research import monte_carlo as module
        from app.engines.research.monte_carlo import MonteCarloEngine

        trades = [1.0, -1.0] * 2_000  # 4,000 trades per path
        summary = MonteCarloEngine.run_simulation(trades, num_simulations=50_000)

        assert summary.num_simulations * summary.num_trades_per_path <= module.MAX_TOTAL_CELLS
        assert summary.num_simulations == module.MAX_TOTAL_CELLS // 4_000

    def test_peak_memory_is_set_by_the_chunk_not_the_request(self) -> None:
        """Finding 9: a maximum-size run stays within a fixed memory envelope."""
        import tracemalloc

        from app.engines.research.monte_carlo import MonteCarloEngine

        tracemalloc.start()
        MonteCarloEngine.run_simulation([1.0, -2.0, 3.0] * 230, num_simulations=50_000)  # 690 trades
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert peak < 400 * 1024 * 1024  # the unpatched engine needed about 1.4 GiB here

    def test_small_runs_are_unchanged_and_reproducible(self) -> None:
        from app.engines.research.monte_carlo import MonteCarloEngine

        trades = [120.0, -80.0, 45.0, -30.0, 200.0, -150.0]
        first = MonteCarloEngine.run_simulation(trades, num_simulations=2_000, seed=7)
        second = MonteCarloEngine.run_simulation(trades, num_simulations=2_000, seed=7)
        assert first == second and first.num_simulations == 2_000


# ── Finding 14: operator alerts ──────────────────────────────────────


class TestOperatorAlerts:
    @pytest.mark.asyncio
    async def test_alert_text_is_escaped_and_the_token_stays_out_of_logs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Finding 14: user text cannot add markup; a failure does not log the bot token."""
        import httpx

        from app.services import notification_service as module

        sent: list[dict[str, Any]] = []
        logged: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            sent.append(json.loads(request.content))
            return httpx.Response(500)  # fail, so the error path is exercised too

        real = httpx.AsyncClient
        monkeypatch.setattr(
            module.httpx, "AsyncClient", lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(handler)})
        )
        monkeypatch.setattr(module.logger, "error", lambda event, **kw: logged.append({"event": event, **kw}))
        settings = get_settings()
        monkeypatch.setattr(settings, "telegram_bot_token", "123456:SECRET-BOT-TOKEN")
        monkeypatch.setattr(settings, "telegram_chat_id", "-100999")
        monkeypatch.setattr(settings, "alert_webhook_url", None)

        ok = await module.NotificationService.send_alert(
            title="Kill switch", message='Reason: <a href="https://evil.example">click</a> & run', level="CRITICAL"
        )

        assert ok is False
        text = sent[0]["text"]
        assert "<a href" not in text and "&lt;a href=" in text and "&amp; run" in text
        assert text.startswith("<b>[CRITICAL] Kill switch</b>")  # the service's own markup survives
        assert logged and "SECRET-BOT-TOKEN" not in repr(logged)


# ── Audit coverage gaps: shared data, jobs and unbounded input ───────


@pytest.mark.integration
class TestBoundedInputs:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("symbol", "timeframe"),
        [("NOTLISTEDUSDT", "1h"), ("BTCUSDT", "7m"), ("A" * 5000, "1h"), ("BTC/USDT", "1h")],
    )
    async def test_history_download_is_limited_to_covered_markets(
        self, client: AsyncClient, auth_headers: dict, symbol: str, timeframe: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Arbitrary symbols must not be fetched into the shared candles table."""
        from app.api.v1.endpoints import market_data

        queued: list[dict[str, Any]] = []
        monkeypatch.setattr(
            market_data.download_historical_klines, "delay", lambda **kw: queued.append(kw)
        )
        response = await client.post(
            "/api/v1/market/download-history",
            headers=auth_headers,
            json={"symbol": symbol, "timeframe": timeframe, "days": 1},
        )
        assert response.status_code == 422
        assert queued == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/market/klines?symbol=" + "A" * 300,
            "/api/v1/market/klines?symbol=BTCUSDT&timeframe=" + "9" * 300,
            "/api/v1/market/klines?symbol=BTCUSDT&offset=99999999999",
            "/api/v1/indicators/" + "A" * 300,
            "/api/v1/strategies/evaluate?strategy_name=../../etc/passwd",
        ],
    )
    async def test_oversized_or_malformed_parameters_are_rejected(
        self, client: AsyncClient, auth_headers: dict, path: str
    ) -> None:
        response = await client.get(path, headers=auth_headers)
        assert response.status_code == 422

    def test_backtest_costs_are_bounded(self) -> None:
        from app.schemas.backtest import BacktestRequest

        for bad in ({"fee_rate": -0.5}, {"slippage": 5.0}, {"initial_capital": float("inf")}, {"symbol": "x" * 500}):
            with pytest.raises(PydanticValidationError):
                BacktestRequest(**bad)

    def test_journal_entries_cannot_store_megabytes(self) -> None:
        from app.schemas.journal import CreateJournalEntryRequest

        base = {"symbol": "BTCUSDT", "direction": "LONG", "entry_price": 50_000.0}
        CreateJournalEntryRequest(**base, user_notes="x" * 1000)  # ordinary use still works
        for bad in (
            {"user_notes": "x" * 200_000},
            {"tags": ["t"] * 500},
            {"indicators_snapshot": {"blob": "x" * 200_000}},
            {"direction": "SIDEWAYS"},
        ):
            with pytest.raises(PydanticValidationError):
                CreateJournalEntryRequest(**{**base, **bad})


@pytest.mark.integration
class TestRetentionPrune:
    @pytest.mark.asyncio
    async def test_expired_rows_are_deleted_in_bounded_chunks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The chunk limit had slid into a comment, so one pass selected every expired row."""
        import inspect

        from app.workers import maintenance

        source = inspect.getsource(maintenance)
        code_lines = [line.split("#", 1)[0] for line in source.splitlines()]
        assert any(".limit(DELETE_CHUNK_SIZE)" in line for line in code_lines)


# ── Audit coverage gap: work done before authentication ──────────────


@pytest.mark.integration
class TestRequestLimits:
    @pytest.mark.asyncio
    async def test_an_oversized_body_is_refused_before_it_is_parsed(self, client: AsyncClient) -> None:
        huge = "x" * (get_settings().max_request_body_bytes + 1)
        response = await client.post("/api/v1/auth/login", json={"email": "a@b.co", "password": huge})
        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_an_ordinary_body_is_unaffected(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/auth/login", json={"email": "nobody@quantx.io", "password": "x"})
        assert response.status_code in {401, 422}

    @pytest.mark.asyncio
    async def test_api_responses_carry_protective_headers(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["cache-control"] == "no-store"

    @pytest.mark.asyncio
    async def test_password_hashing_does_not_block_the_event_loop(self, client: AsyncClient) -> None:
        """bcrypt runs in a worker thread, so the loop keeps serving while it works."""
        import time

        longest_gap = 0.0
        running = True

        async def heartbeat() -> None:
            nonlocal longest_gap
            last = time.perf_counter()
            while running:
                await asyncio.sleep(0.005)
                now = time.perf_counter()
                longest_gap = max(longest_gap, now - last)
                last = now

        beat = asyncio.create_task(heartbeat())
        await asyncio.sleep(0.02)
        await client.post("/api/v1/auth/login", json={"email": "nobody@quantx.io", "password": "Wrong1Pass"})
        running = False
        await beat

        # One bcrypt verify takes roughly 0.2 s. Inline, the heartbeat would stall for all of it.
        assert longest_gap < 0.1


@pytest.mark.integration
class TestExperimentOwnership:
    @pytest.mark.asyncio
    async def test_a_user_sees_only_their_own_experiments(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        second_user: User,
        auth_headers: dict,
        second_user_headers: dict,
        admin_headers: dict,
    ) -> None:
        """Experiments used to be listed to every user."""
        from app.services.experiment_service import ExperimentRegistryService

        service = ExperimentRegistryService(db_session)
        for owner in (test_user.id, second_user.id, None):
            await service.register_experiment(
                user_id=owner, strategy_name="ema_crossover", parameters={}, dataset_version="d" * 64,
                symbol="BTCUSDT", timeframe="1h", start_date="", end_date="", fees=0.0, slippage=0.0, metrics={},
            )
        await db_session.commit()

        mine = (await client.get("/api/v1/research/experiments", headers=auth_headers)).json()
        theirs = (await client.get("/api/v1/research/experiments", headers=second_user_headers)).json()
        everything = (await client.get("/api/v1/research/experiments", headers=admin_headers)).json()

        assert len(mine) == 1 and len(theirs) == 1
        assert mine[0]["experiment_id"] != theirs[0]["experiment_id"]
        assert len(everything) == 3


@pytest.mark.integration
class TestOperatorCli:
    @pytest.mark.asyncio
    async def test_granting_and_revoking_live_trading(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The only way to gain the permission is the operator command."""
        from app import cli

        monkeypatch.setattr(cli, "get_session_factory", lambda: test_session_factory)
        user_id = uuid.uuid4()
        email = f"cli-{user_id.hex[:8]}@quantx.io"
        async with test_session_factory() as session:
            session.add(User(id=user_id, email=email, username=f"cli{user_id.hex[:8]}", hashed_password="x" * 60))
            await session.commit()
        try:
            assert await cli._set_live_trading(email.upper(), True) == 0
            async with test_session_factory() as session:
                assert (await session.get(User, user_id)).can_trade_live is True  # type: ignore[union-attr]
            assert await cli._set_live_trading(email, False) == 0
            async with test_session_factory() as session:
                assert (await session.get(User, user_id)).can_trade_live is False  # type: ignore[union-attr]
            assert await cli._set_live_trading("nobody@quantx.io", True) == 1
        finally:
            async with test_session_factory() as session:
                user = await session.get(User, user_id)
                if user is not None:
                    await session.delete(user)
                    await session.commit()


@pytest.mark.integration
class TestMetricLabels:
    @pytest.mark.asyncio
    async def test_unknown_symbols_share_one_metric_series(self, db_session: AsyncSession, test_user: User) -> None:
        """A caller-chosen symbol must not become its own permanent metric label."""
        from app.core.metrics import TRADES_EXECUTED_TOTAL

        def series() -> set[str]:
            return {s.labels["symbol"] for m in TRADES_EXECUTED_TOTAL.collect() for s in m.samples}

        service = LiveTradingService(db_session, client=StubBinanceClient())
        for symbol in ("ZZZAAA", "ZZZBBB", "ZZZCCC"):
            with pytest.raises(RiskLimitExceededError):
                await service.execute_live_order(test_user.id, order_request(symbol=symbol, side="SELL"))

        assert "OTHER" in series()
        assert not {"ZZZAAA", "ZZZBBB", "ZZZCCC"} & series()
