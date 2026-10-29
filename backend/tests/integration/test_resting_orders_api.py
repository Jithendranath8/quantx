"""
QuantX — Integration Tests for resting paper orders over HTTP.
"""

import pytest
from httpx import AsyncClient

# These tests exercise fills and bookkeeping with large round lots; the risk
# gate is covered separately in tests/unit/test_paper_risk_gate.py.
pytestmark = pytest.mark.usefixtures("relaxed_risk_limits")


@pytest.mark.integration
class TestRestingOrderEndpoints:
    """Placing, listing, triggering and cancelling resting orders."""

    @pytest.mark.asyncio
    async def test_limit_order_rests_then_triggers(
        self, client: AsyncClient, auth_headers: dict, stub_binance
    ) -> None:
        """A limit below the market rests, then fills when price reaches it."""
        account_id = (
            await client.post(
                "/api/v1/paper/accounts",
                json={"initial_balance": 100000.0},
                headers=auth_headers,
            )
        ).json()["id"]

        placed = await client.post(
            "/api/v1/paper/orders",
            headers=auth_headers,
            json={
                "account_id": account_id,
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 0.5,
                "price": 48000.0,
            },
        )
        assert placed.status_code == 201
        assert placed.json()["status"] == "PENDING"

        pending = await client.get(
            f"/api/v1/paper/accounts/{account_id}/pending", headers=auth_headers
        )
        assert len(pending.json()) == 1

        # The stub prices BTCUSDT at 50,000, above the limit.
        result = await client.post(
            f"/api/v1/paper/accounts/{account_id}/process-pending", headers=auth_headers
        )
        assert result.json()["triggered"] == 0
        assert result.json()["still_pending"] == 1

        stub_binance.price = 47_900.0
        result = await client.post(
            f"/api/v1/paper/accounts/{account_id}/process-pending", headers=auth_headers
        )
        assert result.json()["triggered"] == 1

        positions = await client.get(
            f"/api/v1/paper/accounts/{account_id}/positions", headers=auth_headers
        )
        assert len(positions.json()) == 1

    @pytest.mark.asyncio
    async def test_cancel_a_resting_order(
        self, client: AsyncClient, auth_headers: dict, stub_binance
    ) -> None:
        """A pending order can be cancelled through the API."""
        account_id = (
            await client.post(
                "/api/v1/paper/accounts",
                json={"initial_balance": 100000.0},
                headers=auth_headers,
            )
        ).json()["id"]

        order_id = (
            await client.post(
                "/api/v1/paper/orders",
                headers=auth_headers,
                json={
                    "account_id": account_id, "symbol": "BTCUSDT", "side": "BUY",
                    "order_type": "LIMIT", "quantity": 0.1, "price": 10000.0,
                },
            )
        ).json()["id"]

        cancelled = await client.delete(f"/api/v1/paper/orders/{order_id}", headers=auth_headers)
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "CANCELLED"

        pending = await client.get(
            f"/api/v1/paper/accounts/{account_id}/pending", headers=auth_headers
        )
        assert pending.json() == []

    @pytest.mark.asyncio
    async def test_incomplete_order_is_rejected(
        self, client: AsyncClient, auth_headers: dict, stub_binance
    ) -> None:
        """A LIMIT with no price is a validation error, not a guess."""
        account_id = (
            await client.post(
                "/api/v1/paper/accounts", json={"initial_balance": 100000.0}, headers=auth_headers
            )
        ).json()["id"]

        response = await client.post(
            "/api/v1/paper/orders",
            headers=auth_headers,
            json={
                "account_id": account_id, "symbol": "BTCUSDT", "side": "BUY",
                "order_type": "LIMIT", "quantity": 0.1,
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_another_user_cannot_cancel_your_order(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict, stub_binance
    ) -> None:
        """Resting orders are ownership-checked like everything else."""
        account_id = (
            await client.post(
                "/api/v1/paper/accounts", json={"initial_balance": 100000.0}, headers=auth_headers
            )
        ).json()["id"]
        order_id = (
            await client.post(
                "/api/v1/paper/orders",
                headers=auth_headers,
                json={
                    "account_id": account_id, "symbol": "BTCUSDT", "side": "BUY",
                    "order_type": "LIMIT", "quantity": 0.1, "price": 10000.0,
                },
            )
        ).json()["id"]

        response = await client.delete(
            f"/api/v1/paper/orders/{order_id}", headers=second_user_headers
        )
        assert response.status_code == 403


@pytest.mark.integration
class TestStreamStatusEndpoint:
    """The frontend checks this before opening a WebSocket."""

    @pytest.mark.asyncio
    async def test_reports_stream_availability(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Ingestion is off in tests, and the endpoint says so."""
        response = await client.get("/api/v1/health/stream", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["status"] == "DISCONNECTED"
        assert "active_connections" in data

    @pytest.mark.asyncio
    async def test_requires_authentication(self, client: AsyncClient) -> None:
        """Stream metadata is not public."""
        assert (await client.get("/api/v1/health/stream")).status_code == 401
