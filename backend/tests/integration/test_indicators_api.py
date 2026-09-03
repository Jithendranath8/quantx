"""
QuantX — Integration Tests for Indicator Endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestIndicatorEndpoints:
    """Multi-timeframe indicator computation and its guardrails."""

    @pytest.mark.asyncio
    async def test_get_indicators(
        self, client: AsyncClient, auth_headers: dict, seeded_candles: int
    ) -> None:
        """Requested timeframes are computed and returned."""
        response = await client.get(
            "/api/v1/indicators/BTCUSDT?timeframes=1h", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTCUSDT"
        assert "1h" in data["indicators"]
        assert "rsi_14" in data["indicators"]["1h"]

    @pytest.mark.asyncio
    async def test_unknown_timeframe_rejected(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """An unsupported timeframe is a validation error."""
        response = await client.get(
            "/api/v1/indicators/BTCUSDT?timeframes=17q", headers=auth_headers
        )
        assert response.status_code == 422
        assert "Unsupported timeframe" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_timeframe_count_is_capped(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """A long timeframe list is refused.

        Each entry costs a query plus a full indicator pass, so an unbounded
        list on this route was a single-request denial of service.
        """
        many = ",".join(["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"])
        response = await client.get(
            f"/api/v1/indicators/BTCUSDT?timeframes={many}", headers=auth_headers
        )
        assert response.status_code == 422
        assert "Too many timeframes" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_duplicate_timeframes_are_collapsed(
        self, client: AsyncClient, auth_headers: dict, seeded_candles: int
    ) -> None:
        """Repeating a timeframe does not multiply the work."""
        response = await client.get(
            "/api/v1/indicators/BTCUSDT?timeframes=1h,1h,1h,1h,1h,1h,1h,1h,1h,1h",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert list(response.json()["indicators"]) == ["1h"]
