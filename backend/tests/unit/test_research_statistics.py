"""
Tests for selection-bias statistics and purged cross-validation.

The statistics are checked against properties that hold by construction:
noise should not look skilful once deflated, a genuine edge should, and a
split must never let a training sample see its test fold.
"""

import math

import numpy as np
import pytest

from app.engines.research.optimization import ParameterOptimizationEngine
from app.engines.research.purged_cv import CombinatorialPurgedKFold, PurgedKFold
from app.engines.research.statistics import (
    deflated_sharpe,
    expected_max_sharpe,
    per_period_sharpe,
    probabilistic_sharpe,
    probability_of_backtest_overfitting,
)
from tests.unit.test_research_engines import make_frame


@pytest.mark.unit
class TestProbabilisticSharpe:
    """PSR behaves like a probability and responds to evidence."""

    def test_normal_returns_match_closed_form(self) -> None:
        """With skew 0 and kurtosis 3 the variance term is 1 + SR^2 / 2."""
        rng = np.random.default_rng(0)
        returns = rng.normal(0.001, 0.01, 50_000)
        sr = returns.mean() / returns.std()
        expected = 0.5 * (1 + math.erf(sr * np.sqrt(len(returns) - 1) / np.sqrt(1 + sr * sr / 2) / np.sqrt(2)))
        assert probabilistic_sharpe(returns) == pytest.approx(expected, abs=0.02)

    def test_strong_edge_is_near_certain(self) -> None:
        returns = np.random.default_rng(1).normal(0.002, 0.01, 2_000)
        assert probabilistic_sharpe(returns) > 0.99

    def test_losing_series_is_near_zero(self) -> None:
        returns = np.random.default_rng(2).normal(-0.002, 0.01, 2_000)
        assert probabilistic_sharpe(returns) < 0.01

    def test_short_or_flat_series_has_no_evidence(self) -> None:
        assert probabilistic_sharpe([0.01, 0.02]) == 0.0
        assert probabilistic_sharpe([0.0] * 100) == 0.0


@pytest.mark.unit
class TestDeflatedSharpe:
    """DSR penalizes the best-of-N selection."""

    def test_expected_max_grows_with_trials(self) -> None:
        assert expected_max_sharpe(1, 1.0) == 0.0
        assert 0 < expected_max_sharpe(10, 1.0) < expected_max_sharpe(1_000, 1.0)

    def test_best_of_many_noise_trials_is_deflated(self) -> None:
        """The luckiest of 200 zero-edge series looks good raw but not deflated.

        The realized maximum beats its expectation about half the time, so a
        single search can land anywhere; averaged over searches DSR sits near 0.5.
        """
        rng = np.random.default_rng(3)
        psrs: list[float] = []
        dsrs: list[float] = []
        for _ in range(20):
            trials = rng.normal(0.0, 0.01, (500, 200))
            sharpes = np.array([per_period_sharpe(trials[:, j]) for j in range(trials.shape[1])])
            best = trials[:, int(np.argmax(sharpes))]
            psrs.append(probabilistic_sharpe(best))
            dsrs.append(deflated_sharpe(best, sharpes))
        assert np.mean(psrs) > 0.95
        assert 0.3 < np.mean(dsrs) < 0.7

    def test_genuine_edge_survives_deflation(self) -> None:
        rng = np.random.default_rng(4)
        trials = rng.normal(0.0, 0.01, (2_000, 50))
        trials[:, 0] += 0.003
        sharpes = [per_period_sharpe(trials[:, j]) for j in range(trials.shape[1])]
        assert deflated_sharpe(trials[:, 0], sharpes) > 0.95

    def test_single_trial_reduces_to_psr(self) -> None:
        returns = np.random.default_rng(5).normal(0.001, 0.01, 500)
        assert deflated_sharpe(returns, [0.1]) == probabilistic_sharpe(returns)


@pytest.mark.unit
class TestProbabilityOfBacktestOverfitting:
    """CSCV distinguishes a persistent winner from noise."""

    def test_pure_noise_is_coin_flip(self) -> None:
        matrix = np.random.default_rng(6).normal(0.0, 0.01, (1_000, 40))
        pbo = probability_of_backtest_overfitting(matrix)
        assert pbo is not None
        assert 0.25 < pbo < 0.75

    def test_persistent_winner_is_not_overfit(self) -> None:
        matrix = np.random.default_rng(7).normal(0.0, 0.01, (1_000, 40))
        matrix[:, 5] += 0.004
        assert probability_of_backtest_overfitting(matrix) == 0.0

    def test_too_little_data_returns_none(self) -> None:
        assert probability_of_backtest_overfitting(np.zeros((10, 5))) is None
        assert probability_of_backtest_overfitting(np.zeros((500, 1))) is None

    def test_odd_block_count_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            probability_of_backtest_overfitting(np.zeros((100, 3)), n_blocks=5)


@pytest.mark.unit
class TestPurgedKFold:
    """No training index sits inside, just before, or just after its test fold."""

    def test_folds_cover_every_sample_once(self) -> None:
        tests = [test for _, test in PurgedKFold(n_splits=5).split(range(103))]
        assert np.array_equal(np.sort(np.concatenate(tests)), np.arange(103))

    def test_purge_and_embargo_are_applied(self) -> None:
        cv = PurgedKFold(n_splits=4, label_horizon=3, embargo_pct=0.05)
        for train, test in cv.split(range(200)):
            lo, hi = int(test.min()), int(test.max()) + 1
            assert not set(train) & set(range(lo - 3, hi + 10))

    def test_invalid_configuration_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            PurgedKFold(n_splits=1)
        with pytest.raises(ValueError):
            list(PurgedKFold(n_splits=5).split(range(3)))


@pytest.mark.unit
class TestCombinatorialPurgedKFold:
    """CPCV enumerates every held-out combination."""

    def test_split_and_path_counts(self) -> None:
        cv = CombinatorialPurgedKFold(n_groups=6, n_test_groups=2)
        splits = list(cv.split(range(600)))
        assert len(splits) == cv.get_n_splits() == 15
        assert cv.n_paths() == 5

    def test_train_never_touches_test_neighbourhood(self) -> None:
        cv = CombinatorialPurgedKFold(n_groups=6, n_test_groups=2, label_horizon=2, embargo_pct=0.01)
        for train, test in cv.split(range(600)):
            test_set = set(test.tolist())
            assert not set(train.tolist()) & test_set
            for t in train:
                assert not {t + 1, t + 2} & test_set  # purged: its label would reach into test

    def test_invalid_configuration_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            CombinatorialPurgedKFold(n_groups=4, n_test_groups=4)


@pytest.mark.unit
class TestOptimizationSelectionBias:
    """The optimizer reports deflated statistics for its winner."""

    def test_statistics_are_reported(self) -> None:
        grid = {"oversold": [20.0, 25.0, 30.0], "overbought": [70.0, 75.0, 80.0]}
        result = ParameterOptimizationEngine.run_optimization("rsi_mean_reversion", make_frame(), param_grid=grid)
        assert result.deflated_sharpe is not None
        assert result.probabilistic_sharpe is not None
        assert 0.0 <= result.deflated_sharpe <= result.probabilistic_sharpe <= 1.0
        assert result.probability_of_backtest_overfitting is not None
        assert "_returns" not in result.model_dump()["top_candidates"][0]

    def test_low_deflated_sharpe_raises_warning(self) -> None:
        grid = {"oversold": [20.0, 30.0], "overbought": [70.0, 80.0]}
        result = ParameterOptimizationEngine.run_optimization("rsi_mean_reversion", make_frame(), param_grid=grid)
        if result.best_candidate is not None and result.best_candidate.total_trades >= 10:
            assert result.deflated_sharpe is not None
            assert result.overfitting_warning == (
                result.deflated_sharpe < 0.95 or (result.probability_of_backtest_overfitting or 0) > 0.5
            )
