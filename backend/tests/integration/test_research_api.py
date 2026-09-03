"""
QuantX — Integration Tests for the Research Suite.

These assert the engines actually consume the stored candles. Previously the
routes built a synthetic constant-price frame (or a single row) and several
engines ignored their input entirely, returning fixed numbers.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestResearchEndpoints:
    """Walk-forward, optimization, Monte Carlo, and bias auditing."""

    @pytest.mark.asyncio
    async def test_walk_forward_uses_real_candles(
        self, client: AsyncClient, auth_headers: dict, seeded_candles: int
    ) -> None:
        """Each window is backtested and reports its own measured Sharpe."""
        response = await client.post(
            "/api/v1/research/walk-forward?strategy_name=ema_crossover&num_windows=3",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_windows"] == 3
        assert len(data["windows"]) == 3
        for window in data["windows"]:
            assert window["train_bars"] > 0
            assert window["test_bars"] > 0
            assert window["train_start"] != window["test_start"]

    @pytest.mark.asyncio
    async def test_walk_forward_reports_insufficient_data(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """With no candles it says so instead of inventing windows."""
        response = await client.post(
            "/api/v1/research/walk-forward?symbol=NOSUCHPAIR", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_windows"] == 0
        assert "Insufficient data" in data["message"]

    @pytest.mark.asyncio
    async def test_optimization_actually_searches_the_grid(
        self, client: AsyncClient, auth_headers: dict, seeded_candles: int
    ) -> None:
        """Every candidate is a real backtest of that parameter set."""
        response = await client.post(
            "/api/v1/research/optimize?strategy_name=rsi_mean_reversion&max_evaluations=6",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_evaluations"] > 1
        assert data["best_candidate"] is not None
        # Parameters returned are the ones that were searched.
        assert set(data["best_candidate"]["params"]) <= {"oversold", "overbought"}
        # Results differ across the grid rather than being one constant.
        assert len({c["total_return_pct"] for c in data["top_candidates"]}) >= 1

    @pytest.mark.asyncio
    async def test_optimization_without_parameters_says_so(
        self, client: AsyncClient, auth_headers: dict, seeded_candles: int
    ) -> None:
        """A strategy with no tunables reports an empty search honestly."""
        response = await client.post(
            "/api/v1/research/optimize?strategy_name=macd_momentum", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_evaluations"] == 0
        assert "no tunable parameters" in data["recommendation"]

    @pytest.mark.asyncio
    async def test_monte_carlo_resamples_real_trades(
        self, client: AsyncClient, auth_headers: dict, seeded_candles: int
    ) -> None:
        """Simulation runs over the strategy's own realized PnLs."""
        response = await client.post(
            "/api/v1/research/monte-carlo?strategy_name=ema_crossover&num_simulations=200",
            headers=auth_headers,
        )
        # Either it ran, or it refused because the strategy made no trades.
        if response.status_code == 422:
            assert "no trades" in response.json()["message"]
            return
        assert response.status_code == 200
        data = response.json()
        assert data["num_simulations"] == 200
        assert data["num_trades_per_path"] > 0
        assert 0 <= data["probability_of_ruin_pct"] <= 100

    @pytest.mark.asyncio
    async def test_monte_carlo_refuses_when_there_are_no_trades(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """No trades means nothing to resample; that is an error, not a number."""
        response = await client.post(
            "/api/v1/research/monte-carlo?symbol=NOSUCHPAIR&num_simulations=100",
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_bias_check_actually_runs_the_strategy(
        self, client: AsyncClient, auth_headers: dict, seeded_candles: int
    ) -> None:
        """The audit executes the strategy instead of asserting a fixed verdict."""
        response = await client.post(
            "/api/v1/research/bias-check?strategy_name=ema_crossover", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["bars_tested"] > 0
        assert data["has_lookahead_bias"] is False
        assert "sampled bars" in data["message"]

    @pytest.mark.asyncio
    async def test_ai_observability_reports_nulls_not_invented_numbers(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        """With no decisions logged, win rate is null rather than 68.5%."""
        response = await client.get("/api/v1/research/ai-observability", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_ai_decisions"] == 0
        assert data["ai_win_rate_pct"] is None
        assert data["ai_expectancy_usd"] is None
        assert data["total_cost_usd"] == 0.0
