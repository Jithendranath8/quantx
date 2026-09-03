"""
QuantX — Integration Tests: authentication is enforced on every protected route.

/live/orders, /live/kill-switch, /risk/circuit-breaker/toggle, the research
suite, the indicator engine and the market-data proxies were all reachable
without a token. This file exists so that cannot regress silently.
"""

import pytest
from httpx import AsyncClient

# (method, path) pairs that must never be reachable without a valid token.
PROTECTED_ROUTES = [
    ("POST", "/api/v1/live/orders"),
    ("GET", "/api/v1/live/orders"),
    ("POST", "/api/v1/live/kill-switch"),
    ("POST", "/api/v1/live/kill-switch/deactivate"),
    ("GET", "/api/v1/live/kill-switch/status"),
    ("GET", "/api/v1/risk/config"),
    ("POST", "/api/v1/risk/validate"),
    ("POST", "/api/v1/risk/circuit-breaker/toggle"),
    ("GET", "/api/v1/risk/state"),
    ("GET", "/api/v1/indicators/BTCUSDT"),
    ("GET", "/api/v1/market/ticker"),
    ("GET", "/api/v1/market/price"),
    ("GET", "/api/v1/market/orderbook"),
    ("GET", "/api/v1/market/klines"),
    ("GET", "/api/v1/market/symbols"),
    ("GET", "/api/v1/market/timeframes"),
    ("GET", "/api/v1/market/coverage"),
    ("POST", "/api/v1/market/sync"),
    ("POST", "/api/v1/market/download-history"),
    ("POST", "/api/v1/backtest/run"),
    ("POST", "/api/v1/backtest/queue"),
    ("GET", "/api/v1/strategies"),
    ("GET", "/api/v1/strategies/evaluate"),
    ("GET", "/api/v1/agent/analyze"),
    ("POST", "/api/v1/research/walk-forward"),
    ("POST", "/api/v1/research/optimize"),
    ("POST", "/api/v1/research/monte-carlo"),
    ("POST", "/api/v1/research/bias-check"),
    ("GET", "/api/v1/research/experiments"),
    ("GET", "/api/v1/research/ai-observability"),
    ("GET", "/api/v1/analytics/portfolio"),
    ("GET", "/api/v1/analytics/export/csv"),
    ("GET", "/api/v1/journal"),
    ("POST", "/api/v1/journal"),
    ("GET", "/api/v1/paper/accounts"),
    ("POST", "/api/v1/paper/accounts"),
    ("POST", "/api/v1/paper/orders"),
    ("GET", "/api/v1/health/system"),
    ("GET", "/api/v1/health/stream"),
    ("GET", "/api/v1/events"),
    ("POST", "/api/v1/monitoring/notifications/test"),
]


@pytest.mark.integration
class TestAuthEnforcement:
    """Every protected route rejects anonymous and forged callers."""

    @pytest.mark.parametrize(("method", "path"), PROTECTED_ROUTES)
    @pytest.mark.asyncio
    async def test_requires_authentication(
        self, client: AsyncClient, method: str, path: str
    ) -> None:
        """No token means 401, never 200."""
        response = await client.request(method, path, json={})
        assert response.status_code == 401, f"{method} {path} returned {response.status_code}"

    @pytest.mark.parametrize(("method", "path"), PROTECTED_ROUTES)
    @pytest.mark.asyncio
    async def test_rejects_invalid_token(
        self, client: AsyncClient, method: str, path: str
    ) -> None:
        """A garbage bearer token is rejected."""
        response = await client.request(
            method, path, json={}, headers={"Authorization": "Bearer not-a-real-token"}
        )
        assert response.status_code == 401, f"{method} {path} returned {response.status_code}"

    @pytest.mark.asyncio
    async def test_refresh_token_is_not_accepted_as_access_token(
        self, client: AsyncClient, test_user
    ) -> None:
        """A refresh token must not authenticate an API call."""
        from app.core.security import create_refresh_token

        token = create_refresh_token(subject=str(test_user.id))
        response = await client.get(
            "/api/v1/risk/config", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401


@pytest.mark.integration
class TestPublicRoutes:
    """The handful of intentionally public routes still work."""

    @pytest.mark.asyncio
    async def test_liveness_probe_is_public(self, client: AsyncClient) -> None:
        """The load balancer probe needs no credentials."""
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_supported_timeframes_is_public(self, client: AsyncClient) -> None:
        """A static reference list is safe to expose."""
        response = await client.get("/api/v1/indicators/timeframes")
        assert response.status_code == 200
        assert "1h" in response.json()["timeframes"]
