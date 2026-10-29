"""
QuantX — Integration Tests for Analytics Endpoints.
"""

import pytest
from httpx import AsyncClient

# These tests exercise fills and bookkeeping with large round lots; the risk
# gate is covered separately in tests/unit/test_paper_risk_gate.py.
pytestmark = pytest.mark.usefixtures("relaxed_risk_limits")


@pytest.mark.integration
class TestAnalyticsEndpoints:
    """Portfolio summary and the CSV export."""

    @pytest.mark.asyncio
    async def test_get_portfolio(self, client: AsyncClient, auth_headers: dict) -> None:
        """The summary is returned for the authenticated user."""
        response = await client.get("/api/v1/analytics/portfolio", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_equity_usd" in data
        assert "cash_balance_usd" in data

    @pytest.mark.asyncio
    async def test_empty_portfolio_is_not_invented(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """A user who has never traded gets zeros, not a fabricated balance."""
        data = (await client.get("/api/v1/analytics/portfolio", headers=auth_headers)).json()
        assert data["total_equity_usd"] == 0.0
        assert data["win_rate_pct"] is None

    @pytest.mark.asyncio
    async def test_export_csv(self, client: AsyncClient, auth_headers: dict) -> None:
        """The export streams CSV with a header row."""
        response = await client.get("/api/v1/analytics/export/csv", headers=auth_headers)
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert response.text.startswith("order_id,")

    @pytest.mark.asyncio
    async def test_export_excludes_other_users_orders(
        self, client: AsyncClient, auth_headers: dict, second_user_headers: dict, stub_binance
    ) -> None:
        """The export is scoped to the caller's own accounts."""
        created = await client.post(
            "/api/v1/paper/accounts", json={"initial_balance": 100000.0}, headers=auth_headers
        )
        await client.post(
            "/api/v1/paper/orders",
            headers=auth_headers,
            json={
                "account_id": created.json()["id"],
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": 1.0,
            },
        )

        mine = await client.get("/api/v1/analytics/export/csv", headers=auth_headers)
        assert "BTCUSDT" in mine.text

        theirs = await client.get("/api/v1/analytics/export/csv", headers=second_user_headers)
        assert "BTCUSDT" not in theirs.text
