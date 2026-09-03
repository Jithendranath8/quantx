"""
QuantX — Integration Tests for Risk Engine Endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestRiskEndpoints:
    """Risk configuration, validation, and the persisted circuit breaker."""

    @pytest.mark.asyncio
    async def test_get_risk_config(self, client: AsyncClient, auth_headers: dict) -> None:
        """The active risk configuration is returned for the caller."""
        response = await client.get("/api/v1/risk/config", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "max_risk_per_trade_pct" in data
        assert "max_leverage" in data

    @pytest.mark.asyncio
    async def test_validate_trade_risk(self, client: AsyncClient, auth_headers: dict) -> None:
        """A compliant trade proposal is approved."""
        response = await client.post(
            "/api/v1/risk/validate",
            headers=auth_headers,
            json={
                "symbol": "BTCUSDT",
                "action": "BUY",
                "account_balance": 10000.0,
                "order_amount_usd": 1000.0,
                "leverage": 2,
                "entry_price": 50000.0,
                "stop_loss_price": 49000.0,
            },
        )
        assert response.status_code == 200
        assert response.json()["is_approved"] is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_toggle_persists(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """Engaging the breaker survives into the next request.

        It used to mutate a module-level object, so the halt applied to one
        worker process and vanished on restart.
        """
        engage = await client.post(
            "/api/v1/risk/circuit-breaker/toggle?active=true&reason=integration-test",
            headers=auth_headers,
        )
        assert engage.status_code == 200
        assert engage.json()["circuit_breaker_active"] is True

        state = await client.get("/api/v1/risk/state", headers=auth_headers)
        assert state.json()["circuit_breaker_active"] is True

        # And it now blocks trades.
        blocked = await client.post(
            "/api/v1/risk/validate",
            headers=auth_headers,
            json={
                "symbol": "BTCUSDT",
                "action": "BUY",
                "account_balance": 10000.0,
                "order_amount_usd": 100.0,
                "entry_price": 50000.0,
            },
        )
        assert blocked.json()["is_approved"] is False

        release = await client.post(
            "/api/v1/risk/circuit-breaker/toggle?active=false", headers=auth_headers
        )
        assert release.json()["circuit_breaker_active"] is False

    @pytest.mark.asyncio
    async def test_circuit_breaker_is_per_user(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict
    ) -> None:
        """One user's halt does not stop everyone else trading."""
        await client.post(
            "/api/v1/risk/circuit-breaker/toggle?active=true", headers=auth_headers
        )
        other = await client.get("/api/v1/risk/state", headers=second_user_headers)
        assert other.json()["circuit_breaker_active"] is False
