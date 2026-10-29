"""
QuantX — Integration Tests for Paper Trading Endpoints.
"""

import pytest
from httpx import AsyncClient

# These tests exercise fills and bookkeeping with large round lots; the risk
# gate is covered separately in tests/unit/test_paper_risk_gate.py.
pytestmark = pytest.mark.usefixtures("relaxed_risk_limits")


@pytest.mark.integration
class TestPaperTradingEndpoints:
    """Accounts, orders, and cross-tenant isolation over HTTP."""

    @pytest.mark.asyncio
    async def test_create_and_fetch_account(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """An account can be created and read back by its owner."""
        created = await client.post(
            "/api/v1/paper/accounts",
            json={"name": "Integration Account", "initial_balance": 100000.0},
            headers=auth_headers,
        )
        assert created.status_code == 201
        account_id = created.json()["id"]

        fetched = await client.get(f"/api/v1/paper/accounts/{account_id}", headers=auth_headers)
        assert fetched.status_code == 200
        assert fetched.json()["name"] == "Integration Account"

    @pytest.mark.asyncio
    async def test_another_user_cannot_read_your_account(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict
    ) -> None:
        """Supplying someone else's account UUID is forbidden, not permitted.

        Every paper-trading route previously took the account id on trust.
        """
        created = await client.post(
            "/api/v1/paper/accounts", json={"initial_balance": 100000.0}, headers=auth_headers
        )
        account_id = created.json()["id"]

        for path in (
            f"/api/v1/paper/accounts/{account_id}",
            f"/api/v1/paper/accounts/{account_id}/positions",
            f"/api/v1/paper/accounts/{account_id}/orders",
        ):
            response = await client.get(path, headers=second_user_headers)
            assert response.status_code == 403, f"{path} returned {response.status_code}"

    @pytest.mark.asyncio
    async def test_another_user_cannot_trade_your_account(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict, stub_binance
    ) -> None:
        """Writes are ownership-checked too, not just reads."""
        created = await client.post(
            "/api/v1/paper/accounts", json={"initial_balance": 100000.0}, headers=auth_headers
        )
        account_id = created.json()["id"]

        response = await client.post(
            "/api/v1/paper/orders",
            headers=second_user_headers,
            json={
                "account_id": account_id,
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": 1.0,
            },
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_buy_then_sell_round_trip(
        self, client: AsyncClient, auth_headers: dict, stub_binance
    ) -> None:
        """A full buy/sell cycle updates balance, position, and PnL."""
        created = await client.post(
            "/api/v1/paper/accounts", json={"initial_balance": 100000.0}, headers=auth_headers
        )
        account_id = created.json()["id"]
        order = {
            "account_id": account_id,
            "symbol": "BTCUSDT",
            "order_type": "MARKET",
            "quantity": 1.0,
        }

        buy = await client.post(
            "/api/v1/paper/orders", headers=auth_headers, json={**order, "side": "BUY"}
        )
        assert buy.status_code == 201

        positions = await client.get(
            f"/api/v1/paper/accounts/{account_id}/positions", headers=auth_headers
        )
        assert len(positions.json()) == 1

        sell = await client.post(
            "/api/v1/paper/orders", headers=auth_headers, json={**order, "side": "SELL"}
        )
        assert sell.status_code == 201

        positions = await client.get(
            f"/api/v1/paper/accounts/{account_id}/positions", headers=auth_headers
        )
        assert positions.json() == []

    @pytest.mark.asyncio
    async def test_accounts_listing_is_scoped(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict
    ) -> None:
        """Listing returns only your own accounts."""
        await client.post(
            "/api/v1/paper/accounts", json={"name": "Mine"}, headers=auth_headers
        )
        response = await client.get("/api/v1/paper/accounts", headers=second_user_headers)
        assert response.status_code == 200
        assert response.json() == []
