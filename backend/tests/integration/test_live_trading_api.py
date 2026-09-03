"""
QuantX — Integration Tests for Live Trading API Endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestLiveTradingEndpoints:
    """Kill switch and order routes."""

    @pytest.mark.asyncio
    async def test_kill_switch_halts_and_reports_honestly(
        self, client: AsyncClient, auth_headers: dict, stub_binance
    ) -> None:
        """The kill switch halts trading and states whether it fully succeeded."""
        response = await client.post("/api/v1/live/kill-switch", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "HALTED"
        assert data["circuit_breaker_active"] is True
        # The success claim is explicit rather than implied.
        assert "fully_successful" in data

    @pytest.mark.asyncio
    async def test_kill_switch_status_and_release(
        self, client: AsyncClient, auth_headers: dict, stub_binance
    ) -> None:
        """Halt state is queryable and reversible."""
        await client.post("/api/v1/live/kill-switch", headers=auth_headers)

        status = await client.get("/api/v1/live/kill-switch/status", headers=auth_headers)
        assert status.json()["circuit_breaker_active"] is True

        await client.post("/api/v1/live/kill-switch/deactivate", headers=auth_headers)
        status = await client.get("/api/v1/live/kill-switch/status", headers=auth_headers)
        assert status.json()["circuit_breaker_active"] is False

    @pytest.mark.asyncio
    async def test_order_without_credentials_is_refused_not_faked(
        self, client: AsyncClient, auth_headers: dict, stub_binance
    ) -> None:
        """With no exchange credentials the order fails loudly.

        It used to return a hardcoded order id with status FILLED without ever
        contacting the exchange.
        """
        response = await client.post(
            "/api/v1/live/orders",
            headers=auth_headers,
            json={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 0.1,
                "price": 50000.0,
            },
        )
        assert response.status_code != 201
        body = response.json()
        assert body.get("error") is True
        assert "LIVE-ORD" not in response.text

    @pytest.mark.asyncio
    async def test_order_blocked_while_halted(
        self, client: AsyncClient, auth_headers: dict, stub_binance
    ) -> None:
        """A halted account cannot place orders."""
        await client.post("/api/v1/live/kill-switch", headers=auth_headers)
        response = await client.post(
            "/api/v1/live/orders",
            headers=auth_headers,
            json={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 0.1,
                "price": 50000.0,
            },
        )
        assert response.status_code == 400
        assert "circuit breaker is ACTIVE" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_order_list_is_scoped_to_the_caller(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict
    ) -> None:
        """Each user sees only their own live orders."""
        response = await client.get("/api/v1/live/orders", headers=second_user_headers)
        assert response.status_code == 200
        assert response.json() == []
