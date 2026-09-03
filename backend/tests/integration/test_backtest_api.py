"""
QuantX — Integration Tests for Backtest REST Endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestBacktestEndpoints:
    """Backtest execution over HTTP."""

    @pytest.mark.asyncio
    async def test_run_backtest(
        self, client: AsyncClient, auth_headers: dict, seeded_candles: int
    ) -> None:
        """A backtest over stored candles returns metrics and an equity curve."""
        response = await client.post(
            "/api/v1/backtest/run",
            headers=auth_headers,
            json={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "strategy_name": "ema_crossover",
                "initial_capital": 10000.0,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTCUSDT"
        assert "metrics" in data
        assert len(data["equity_curve"]) > 0
        assert data["final_equity"] > 0

    @pytest.mark.asyncio
    async def test_backtest_without_data_is_empty_not_fabricated(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """No candles produces an empty result, not invented performance."""
        response = await client.post(
            "/api/v1/backtest/run",
            headers=auth_headers,
            json={"symbol": "NOSUCHPAIR", "timeframe": "1h", "strategy_name": "ema_crossover"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["equity_curve"] == []
        assert data["metrics"]["total_trades"] == 0

    @pytest.mark.asyncio
    async def test_inverted_date_range_rejected(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """start_date after end_date is a validation error, not a silent empty run."""
        response = await client.post(
            "/api/v1/backtest/run",
            headers=auth_headers,
            json={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "strategy_name": "ema_crossover",
                "start_date": "2026-06-01T00:00:00Z",
                "end_date": "2026-01-01T00:00:00Z",
            },
        )
        assert response.status_code == 422
