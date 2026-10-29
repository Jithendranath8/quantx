"""
QuantX — Selection-bias statistics for strategy research.

A Sharpe ratio picked as the best of many trials is biased upward: with enough
attempts, noise alone produces an impressive winner. These functions quantify
how much of a result survives that correction.

- Probabilistic Sharpe Ratio (PSR): probability the true Sharpe exceeds a
  benchmark, accounting for sample length, skew and fat tails.
  Bailey & López de Prado (2012), "The Sharpe Ratio Efficient Frontier".
- Deflated Sharpe Ratio (DSR): PSR against the Sharpe you would expect from the
  best of N zero-edge trials. Bailey & López de Prado (2014), "The Deflated
  Sharpe Ratio".
- Probability of Backtest Overfitting (PBO) via Combinatorially Symmetric
  Cross-Validation (CSCV): how often the in-sample winner ranks below the
  median out of sample. Bailey, Borwein, López de Prado & Zhu (2017).

All Sharpe ratios here are per-period (not annualized); that is the unit the
PSR standard error is derived in.
"""

import math
from itertools import combinations
from statistics import NormalDist

import numpy as np

EULER_MASCHERONI = 0.5772156649015329
_STD_EPS = 1e-12
_NORMAL = NormalDist()

# CSCV evaluates C(S, S/2) splits; 10 blocks gives 252, enough resolution for
# a stable PBO without making a 200-trial search slow.
DEFAULT_CSCV_BLOCKS = 10


def _clean(returns: np.ndarray | list[float]) -> np.ndarray:
    arr = np.asarray(returns, dtype=float).ravel()
    return arr[np.isfinite(arr)]


def per_period_sharpe(returns: np.ndarray | list[float]) -> float:
    """Mean over standard deviation of a return series, not annualized."""
    arr = _clean(returns)
    if arr.size < 2:
        return 0.0
    std = float(arr.std(ddof=1))
    if std < _STD_EPS:
        return 0.0
    return float(arr.mean() / std)


def probabilistic_sharpe(returns: np.ndarray | list[float], sr_benchmark: float = 0.0) -> float:
    """P(true Sharpe > ``sr_benchmark``) given the observed, possibly non-normal, returns.

    The standard error uses raw (non-excess) kurtosis, so a normal series has
    kurtosis 3 and the variance term reduces to ``1 + SR**2 / 2``.
    """
    arr = _clean(returns)
    n = arr.size
    if n < 5:
        return 0.0
    std = float(arr.std(ddof=0))
    if std < _STD_EPS:
        return 0.0
    centred = arr - arr.mean()
    sr = float(arr.mean() / std)
    skew = float((centred**3).mean() / std**3)
    kurtosis = float((centred**4).mean() / std**4)

    variance = 1.0 - skew * sr + (kurtosis - 1.0) / 4.0 * sr * sr
    if variance <= 0:
        return 0.0
    z = (sr - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(variance)
    return _NORMAL.cdf(z)


def expected_max_sharpe(n_trials: int, trial_sharpe_variance: float) -> float:
    """Expected best per-period Sharpe among ``n_trials`` trials that have no edge."""
    if n_trials < 2 or trial_sharpe_variance <= 0:
        return 0.0
    n = float(n_trials)
    expected_max_z = (1.0 - EULER_MASCHERONI) * _NORMAL.inv_cdf(1.0 - 1.0 / n) + EULER_MASCHERONI * _NORMAL.inv_cdf(
        1.0 - 1.0 / (n * math.e)
    )
    return math.sqrt(trial_sharpe_variance) * expected_max_z


def deflated_sharpe(returns: np.ndarray | list[float], trial_sharpes: np.ndarray | list[float]) -> float:
    """PSR of the selected strategy against the expected maximum of the search.

    ``trial_sharpes`` are the per-period Sharpe ratios of every trial run,
    including the selected one. The penalty grows with both the number of
    trials and how widely their Sharpes spread. Counting every trial as
    independent is conservative when parameter sets are correlated.
    """
    trials = _clean(trial_sharpes)
    if trials.size < 2:
        return probabilistic_sharpe(returns)
    benchmark = expected_max_sharpe(int(trials.size), float(trials.var(ddof=1)))
    return probabilistic_sharpe(returns, sr_benchmark=benchmark)


def probability_of_backtest_overfitting(
    returns_matrix: np.ndarray,
    n_blocks: int = DEFAULT_CSCV_BLOCKS,
) -> float | None:
    """PBO by CSCV over a ``(bars, trials)`` matrix of per-bar returns.

    Rows are split into ``n_blocks`` contiguous blocks. For every way of
    choosing half the blocks as in-sample, the trial with the best in-sample
    Sharpe is located in the out-of-sample ranking. PBO is the fraction of
    splits in which that winner lands at or below the OOS median, i.e. where
    picking the in-sample best was no better than picking at random.

    Returns None when there are too few trials or bars to form the splits.
    """
    matrix = np.asarray(returns_matrix, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("returns_matrix must be 2-D (bars, trials)")
    if n_blocks < 2 or n_blocks % 2:
        raise ValueError("n_blocks must be an even number >= 2")
    n_bars, n_trials = matrix.shape
    if n_trials < 2 or n_bars < n_blocks * 2:
        return None

    matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)
    # Per-block sufficient statistics let each split's Sharpe be assembled from
    # block sums instead of re-scanning the bars.
    blocks = np.array_split(matrix, n_blocks, axis=0)
    counts = np.array([b.shape[0] for b in blocks], dtype=float)
    sums = np.stack([b.sum(axis=0) for b in blocks])
    squares = np.stack([(b * b).sum(axis=0) for b in blocks])

    def split_sharpe(idx: list[int]) -> np.ndarray:
        n = counts[idx].sum()
        mean = sums[idx].sum(axis=0) / n
        var = squares[idx].sum(axis=0) / n - mean * mean
        std = np.sqrt(np.clip(var, 0.0, None))
        out = np.zeros(n_trials)
        np.divide(mean, std, out=out, where=std > _STD_EPS)
        return out

    all_blocks = set(range(n_blocks))
    overfit = 0
    total = 0
    for in_sample in combinations(range(n_blocks), n_blocks // 2):
        is_sr = split_sharpe(list(in_sample))
        oos_sr = split_sharpe(sorted(all_blocks.difference(in_sample)))
        winner = int(np.argmax(is_sr))
        # Relative OOS rank in (0, 1); 1 is best. Ties count against the winner.
        rank = int((oos_sr < oos_sr[winner]).sum()) + 1
        omega = rank / (n_trials + 1)
        if omega <= 0.5:
            overfit += 1
        total += 1
    return overfit / total
