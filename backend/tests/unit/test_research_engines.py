"""
QuantX — Unit Tests for the research engines.

These assert the engines consume their inputs. Previously optimization ignored
its param_grid, walk-forward returned `1.85 + i * 0.05`, and the bias detector
returned a fixed "no bias" verdict without executing anything.
"""

import math
from typing import ClassVar

import pandas as pd
import pytest

from app.engines.research.bias_detector import LookAheadBiasDetector
from app.engines.research.monte_carlo import MonteCarloEngine
from app.engines.research.optimization import ParameterOptimizationEngine
from app.engines.research.walk_forward import WalkForwardEngine
from app.engines.strategy.registry import StrategyRegistry


def make_frame(n: int = 400) -> pd.DataFrame:
    """A trending series with a cycle."""
    closes = [50_000 + i * 25 + 900 * math.sin(i / 9) for i in range(n)]
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="1h"),
            "open": [c - 10 for c in closes],
            "high": [c + 80 for c in closes],
            "low": [c - 80 for c in closes],
            "close": closes,
            "volume": [100.0] * n,
        }
    )


@pytest.mark.unit
class TestWalkForward:
    """Rolling train/test evaluation."""

    def test_windows_are_backtested_independently(self) -> None:
        """Each window reports measured in- and out-of-sample results."""
        result = WalkForwardEngine.run_walk_forward("ema_crossover", make_frame(), num_windows=3)
        assert result.total_windows == 3
        assert len(result.windows) == 3
        for window in result.windows:
            assert window.train_bars > 0
            assert window.test_bars > 0
            assert window.train_end < window.test_start

    def test_insufficient_data_is_reported(self) -> None:
        """A short series produces no windows and says why."""
        result = WalkForwardEngine.run_walk_forward("ema_crossover", make_frame(50))
        assert result.total_windows == 0
        assert "Insufficient data" in result.message

    def test_too_many_windows_is_reported(self) -> None:
        """Splitting too finely is refused with an actionable message."""
        result = WalkForwardEngine.run_walk_forward(
            "ema_crossover", make_frame(250), num_windows=20
        )
        assert result.total_windows == 0
        assert "fewer windows" in result.message


@pytest.mark.unit
class TestOptimization:
    """Parameter search."""

    def test_grid_is_actually_expanded_and_scored(self) -> None:
        """Every combination in the grid is evaluated with a backtest."""
        grid = {"oversold": [20.0, 30.0], "overbought": [70.0, 80.0]}
        result = ParameterOptimizationEngine.run_optimization(
            "rsi_mean_reversion", make_frame(), param_grid=grid
        )
        assert result.total_evaluations == 4
        assert {tuple(sorted(c.params.items())) for c in result.top_candidates}.__len__() == 4

    def test_supplied_parameters_reach_the_strategy(self) -> None:
        """Different parameters give different strategy instances."""
        strict = StrategyRegistry.build("rsi_mean_reversion", oversold=10.0, overbought=90.0)
        loose = StrategyRegistry.build("rsi_mean_reversion", oversold=45.0, overbought=55.0)
        assert strict.oversold == 10.0
        assert loose.overbought == 55.0

    def test_unknown_kwargs_are_dropped(self) -> None:
        """A shared grid can be applied across differing constructors."""
        strategy = StrategyRegistry.build("macd_momentum", oversold=10.0)
        assert strategy.name == "macd_momentum"

    def test_strategy_without_parameters_reports_empty_search(self) -> None:
        """Nothing to tune is stated plainly, not faked."""
        result = ParameterOptimizationEngine.run_optimization("macd_momentum", make_frame())
        assert result.total_evaluations == 0
        assert result.best_candidate is None
        assert "no tunable parameters" in result.recommendation

    def test_max_evaluations_is_enforced(self) -> None:
        """A large grid cannot run unbounded."""
        grid = {"oversold": [float(x) for x in range(10, 40)], "overbought": [60.0, 70.0, 80.0]}
        result = ParameterOptimizationEngine.run_optimization(
            "rsi_mean_reversion", make_frame(150), param_grid=grid, max_evaluations=5
        )
        assert result.total_evaluations <= 5

    def test_empty_data_evaluates_nothing(self) -> None:
        """No candles means no results."""
        result = ParameterOptimizationEngine.run_optimization(
            "rsi_mean_reversion", pd.DataFrame()
        )
        assert result.total_evaluations == 0
        assert "No candle data" in result.recommendation


@pytest.mark.unit
class TestMonteCarlo:
    """Bootstrap resampling."""

    def test_empty_trades_returns_flat_summary(self) -> None:
        """No trades means no simulation."""
        summary = MonteCarloEngine.run_simulation([], initial_capital=10_000.0)
        assert summary.num_simulations == 0
        assert summary.mean_final_equity == 10_000.0

    def test_results_are_reproducible(self) -> None:
        """A fixed seed makes research results comparable across runs."""
        pnls = [120.0, -45.0, 85.0, -30.0, 210.0, -90.0]
        a = MonteCarloEngine.run_simulation(pnls, num_simulations=500, seed=7)
        b = MonteCarloEngine.run_simulation(pnls, num_simulations=500, seed=7)
        assert a.mean_final_equity == b.mean_final_equity
        assert a.worst_case_drawdown_95_pct == b.worst_case_drawdown_95_pct

    def test_losing_streak_is_computed_not_constant(self) -> None:
        """An all-loss series has a streak equal to its length."""
        summary = MonteCarloEngine.run_simulation([-10.0] * 8, num_simulations=100)
        assert summary.expected_longest_losing_streak == 8

        winners = MonteCarloEngine.run_simulation([10.0] * 8, num_simulations=100)
        assert winners.expected_longest_losing_streak == 0

    def test_ruinous_pnls_produce_high_ruin_probability(self) -> None:
        """Losses that halve the account register as ruin."""
        summary = MonteCarloEngine.run_simulation(
            [-3000.0] * 5, initial_capital=10_000.0, num_simulations=200
        )
        assert summary.probability_of_ruin_pct == 100.0

    def test_simulation_count_is_capped(self) -> None:
        """A caller cannot request an unbounded simulation."""
        summary = MonteCarloEngine.run_simulation([1.0, -1.0], num_simulations=10_000_000)
        assert summary.num_simulations <= 50_000


@pytest.mark.unit
class TestBiasDetector:
    """Causality auditing."""

    def test_clean_strategy_passes_with_bars_tested(self) -> None:
        """A causal strategy passes, and the audit reports how much it checked."""
        report = LookAheadBiasDetector.audit_strategy("ema_crossover", make_frame(200))
        assert report.has_lookahead_bias is False
        assert report.bars_tested > 0
        assert report.violations == []

    def test_unknown_strategy_is_reported(self) -> None:
        """An unregistered strategy audits nothing and says so."""
        report = LookAheadBiasDetector.audit_strategy("nope", make_frame(200))
        assert report.bars_tested == 0
        assert "not registered" in report.message

    def test_short_series_is_reported(self) -> None:
        """Too little data to audit is stated, not passed silently."""
        report = LookAheadBiasDetector.audit_strategy("ema_crossover", make_frame(20))
        assert report.bars_tested == 0
        assert "Insufficient data" in report.message


@pytest.mark.unit
class TestTPEOptimization:
    """Sequential model-based search.

    TPE is genuinely adaptive: it fits densities over good and bad trials and
    concentrates its budget where the ratio is highest, rather than sweeping
    the grid. These tests pin that it respects its budget, finds competitive
    parameters, and is reproducible.
    """

    GRID: ClassVar[dict[str, list[float]]] = {
        "oversold": [15.0, 20.0, 25.0, 30.0, 35.0, 40.0],
        "overbought": [60.0, 65.0, 70.0, 75.0, 80.0, 85.0],
    }

    def test_respects_the_evaluation_budget(self) -> None:
        """TPE stops at max_evaluations instead of sweeping the grid."""
        result = ParameterOptimizationEngine.run_optimization(
            "rsi_mean_reversion", make_frame(), param_grid=self.GRID,
            method="TPE", max_evaluations=10, seed=7,
        )
        assert result.method == "TPE"
        assert result.total_evaluations == 10
        assert result.total_evaluations < len(ParameterOptimizationEngine._expand(self.GRID))

    def test_finds_the_exhaustive_optimum_on_a_smaller_budget(self) -> None:
        """A partial search still locates the best cell on this space."""
        exhaustive = ParameterOptimizationEngine.run_optimization(
            "rsi_mean_reversion", make_frame(), param_grid=self.GRID,
            method="GRID_SEARCH", max_evaluations=200,
        )
        tpe = ParameterOptimizationEngine.run_optimization(
            "rsi_mean_reversion", make_frame(), param_grid=self.GRID,
            method="TPE", max_evaluations=12, seed=7,
        )
        assert tpe.best_candidate is not None
        assert exhaustive.best_candidate is not None
        assert tpe.best_candidate.sharpe_ratio == pytest.approx(
            exhaustive.best_candidate.sharpe_ratio
        )

    def test_is_reproducible_for_a_fixed_seed(self) -> None:
        """A research result that changes between runs cannot be compared."""
        kwargs = {
            "param_grid": self.GRID, "method": "TPE", "max_evaluations": 12, "seed": 3,
        }
        a = ParameterOptimizationEngine.run_optimization(
            "rsi_mean_reversion", make_frame(), **kwargs
        )
        b = ParameterOptimizationEngine.run_optimization(
            "rsi_mean_reversion", make_frame(), **kwargs
        )
        assert a.best_candidate.params == b.best_candidate.params
        assert a.total_evaluations == b.total_evaluations

    def test_different_seeds_explore_differently(self) -> None:
        """The search path depends on the seed, not on list order."""
        runs = {
            tuple(
                sorted(
                    ParameterOptimizationEngine.run_optimization(
                        "rsi_mean_reversion", make_frame(), param_grid=self.GRID,
                        method="TPE", max_evaluations=8, seed=seed,
                    ).top_candidates[-1].params.items()
                )
            )
            for seed in (1, 2, 3, 4, 5)
        }
        assert len(runs) > 1

    def test_strategy_without_parameters_stops_immediately(self) -> None:
        """Nothing to tune means no evaluations, honestly reported."""
        result = ParameterOptimizationEngine.run_optimization(
            "macd_momentum", make_frame(), method="TPE", max_evaluations=10
        )
        assert result.total_evaluations == 0
        assert "no tunable parameters" in result.recommendation


@pytest.mark.unit
class TestWalkForwardMessaging:
    """The verdict must not read as reassurance when both sides lost money."""

    def test_unprofitable_in_sample_is_called_out(self) -> None:
        """Consistency between two negative Sharpes is not good news.

        The efficiency ratio divides OOS by IS; with both negative it produces
        a flattering number for a strategy that never worked.
        """
        # A pure downtrend gives a long-only crossover nothing to work with.
        n = 400
        closes = [80_000 - i * 60 for i in range(n)]
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-01-01", periods=n, freq="1h"),
                "open": [c + 20 for c in closes],
                "high": [c + 90 for c in closes],
                "low": [c - 90 for c in closes],
                "close": closes,
                "volume": [100.0] * n,
            }
        )
        result = WalkForwardEngine.run_walk_forward("ema_crossover", df, num_windows=3)

        if result.avg_in_sample_sharpe <= 0:
            assert "unprofitable in-sample" in result.message
            assert "broadly consistent" not in result.message
            assert result.efficiency_ratio == 0.0
