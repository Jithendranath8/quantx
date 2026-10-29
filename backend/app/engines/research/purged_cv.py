"""
QuantX — Purged and embargoed cross-validation for time series.

Ordinary k-fold leaks on financial data: a training sample's label is built
from bars that may sit inside the test fold, and serial correlation carries
information across the boundary. López de Prado, "Advances in Financial
Machine Learning" (2018), ch. 7 and 12, fixes this by:

- purging training samples whose label horizon reaches into a test fold, and
- embargoing a buffer of samples immediately after each test fold.

``CombinatorialPurgedKFold`` holds out every combination of ``n_test_groups``
groups, producing many out-of-sample paths from one history instead of one.

Both splitters yield ``(train_idx, test_idx)`` positional index arrays, the
same contract as scikit-learn's ``KFold.split``.
"""

from collections.abc import Iterator, Sized
from dataclasses import dataclass
from itertools import combinations
from math import comb

import numpy as np


def _bounds(n: int, groups: int) -> list[tuple[int, int]]:
    size = n // groups
    return [(k * size, (k + 1) * size if k < groups - 1 else n) for k in range(groups)]


def _purge_and_embargo(keep: np.ndarray, lo: int, hi: int, label_horizon: int, embargo: int) -> None:
    keep[max(0, lo - label_horizon) : lo] = False
    keep[hi : hi + embargo] = False


@dataclass(frozen=True)
class PurgedKFold:
    """Sequential k-fold with purging and a post-test embargo.

    Args:
        n_splits: Number of contiguous, non-overlapping test folds.
        label_horizon: Bars a label looks forward (1 for next-bar direction).
        embargo_pct: Fraction of all samples dropped after each test fold.
    """

    n_splits: int = 5
    label_horizon: int = 1
    embargo_pct: float = 0.01

    def __post_init__(self) -> None:
        if self.n_splits < 2:
            raise ValueError("n_splits must be >= 2")
        if self.label_horizon < 0 or self.embargo_pct < 0:
            raise ValueError("label_horizon and embargo_pct must be non-negative")

    def split(self, x: Sized) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        n = len(x)
        if n < self.n_splits:
            raise ValueError(f"Cannot split {n} samples into {self.n_splits} folds")
        embargo = round(self.embargo_pct * n)
        indices = np.arange(n)
        for lo, hi in _bounds(n, self.n_splits):
            keep = np.ones(n, dtype=bool)
            keep[lo:hi] = False
            _purge_and_embargo(keep, lo, hi, self.label_horizon, embargo)
            yield indices[keep], indices[lo:hi]

    def get_n_splits(self) -> int:
        return self.n_splits


@dataclass(frozen=True)
class CombinatorialPurgedKFold:
    """Combinatorial purged CV (CPCV): every choice of ``n_test_groups`` held-out groups.

    Each group appears in ``n_test_groups * n_splits / n_groups`` test sets, so
    stitching the held-out predictions together yields ``n_paths`` complete
    out-of-sample backtest paths.
    """

    n_groups: int = 6
    n_test_groups: int = 2
    label_horizon: int = 1
    embargo_pct: float = 0.01

    def __post_init__(self) -> None:
        if not 1 <= self.n_test_groups < self.n_groups:
            raise ValueError("Need 1 <= n_test_groups < n_groups")
        if self.label_horizon < 0 or self.embargo_pct < 0:
            raise ValueError("label_horizon and embargo_pct must be non-negative")

    def split(self, x: Sized) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        n = len(x)
        if n < self.n_groups:
            raise ValueError(f"Cannot split {n} samples into {self.n_groups} groups")
        bounds = _bounds(n, self.n_groups)
        embargo = round(self.embargo_pct * n)
        indices = np.arange(n)
        for held_out in combinations(range(self.n_groups), self.n_test_groups):
            test = np.zeros(n, dtype=bool)
            for g in held_out:
                lo, hi = bounds[g]
                test[lo:hi] = True
            keep = ~test
            for g in held_out:
                lo, hi = bounds[g]
                _purge_and_embargo(keep, lo, hi, self.label_horizon, embargo)
            yield indices[keep], indices[test]

    def get_n_splits(self) -> int:
        return comb(self.n_groups, self.n_test_groups)

    def n_paths(self) -> int:
        return self.get_n_splits() * self.n_test_groups // self.n_groups
