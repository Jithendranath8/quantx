"""
QuantX — Integration Tests for Strategy Endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestStrategyEndpoints:
    """Strategy listing and evaluation."""

    @pytest.mark.asyncio
    async def test_list_strategies(self, client: AsyncClient, auth_headers: dict) -> None:
        """Every registered strategy is listed with its description."""
        response = await client.get("/api/v1/strategies", headers=auth_headers)
        assert response.status_code == 200
        names = [s["name"] for s in response.json()]
        assert "ema_crossover" in names
        assert "rsi_mean_reversion" in names

    @pytest.mark.asyncio
    async def test_evaluate_strategy(
        self, client: AsyncClient, auth_headers: dict, seeded_candles: int
    ) -> None:
        """Evaluation over stored candles returns a signal."""
        response = await client.get(
            "/api/v1/strategies/evaluate?strategy_name=ema_crossover&symbol=BTCUSDT&timeframe=1h",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action"] in {"BUY", "SELL", "WAIT"}
        assert "confidence" in data
        assert "reasoning" in data

    @pytest.mark.asyncio
    async def test_evaluate_without_data_waits(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """With no candles stored the engine waits rather than inventing a signal."""
        response = await client.get(
            "/api/v1/strategies/evaluate?strategy_name=ema_crossover&symbol=NOSUCHPAIR",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["action"] == "WAIT"
