"""
QuantX — Parameter Optimization Engine.

Grid and random search over strategy parameters, scored by real backtests.

Every candidate below is produced by running the backtest engine with those
parameters. The previous implementation ignored ``param_grid`` entirely and
returned two hardcoded candidates with an "out-of-sample performance is stable"
recommendation, which is a fabricated research result.
"""

import itertools
import math
import random
from collections.abc import Callable
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel

from app.engines.backtest.engine import BacktestEngine
from app.engines.strategy.registry import StrategyRegistry
from app.schemas.backtest import BacktestRequest

MAX_EVALUATIONS = 200
# TPE: fraction of the budget spent exploring randomly before exploiting, and
# the top quantile of trials treated as "good" when building the densities.
TPE_WARMUP_FRACTION = 0.35
TPE_MIN_WARMUP = 5
TPE_GOOD_QUANTILE = 0.25


class OptimizationCandidate(BaseModel):
    """One parameter set and the performance it produced."""

    params: dict[str, Any]
    sharpe_ratio: float
    sortino_ratio: float
    total_return_pct: float
    max_drawdown_pct: float
    profit_factor: float
    total_trades: int


class OptimizationResult(BaseModel):
    """Outcome of a parameter search."""

    strategy_name: str
    symbol: str
    timeframe: str
    method: Literal["GRID_SEARCH", "RANDOM_SEARCH", "TPE"]
    total_evaluations: int
    best_candidate: OptimizationCandidate | None
    top_candidates: list[OptimizationCandidate]
    overfitting_warning: bool
    recommendation: str


class ParameterOptimizationEngine:
    """Optimizes strategy parameters across hyperparameter grids."""

    @staticmethod
    def run_optimization(
        strategy_name: str,
        df_candles: pd.DataFrame,
        param_grid: dict[str, list[Any]] | None = None,
        method: Literal["GRID_SEARCH", "RANDOM_SEARCH", "TPE"] = "GRID_SEARCH",
        symbol: str = "BTCUSDT",
        timeframe: str = "1h",
        initial_capital: float = 10_000.0,
        max_evaluations: int = MAX_EVALUATIONS,
        seed: int = 42,
    ) -> OptimizationResult:
        """Search a parameter space, scoring each candidate with a backtest.

        Args:
            strategy_name: Registered strategy to optimize.
            df_candles: Chronological OHLCV frame to evaluate against.
            param_grid: Search space; defaults to the strategy's own grid.
            method: GRID_SEARCH evaluates every combination. RANDOM_SEARCH
                samples the grid uniformly. TPE is sequential model-based
                optimization: it fits densities over good and bad trials and
                samples where their ratio is highest.
            max_evaluations: Hard cap so a large grid cannot run unbounded.
            seed: Makes RANDOM_SEARCH reproducible.
        """
        grid = param_grid if param_grid else StrategyRegistry.default_param_grid(strategy_name)
        combinations = ParameterOptimizationEngine._expand(grid)

        if method == "RANDOM_SEARCH" and len(combinations) > max_evaluations:
            combinations = random.Random(seed).sample(combinations, max_evaluations)
        elif method != "TPE":
            combinations = combinations[:max_evaluations]

        if df_candles.empty:
            return OptimizationResult(
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                method=method,
                total_evaluations=0,
                best_candidate=None,
                top_candidates=[],
                overfitting_warning=False,
                recommendation="No candle data supplied; nothing was evaluated.",
            )

        scorer = ParameterOptimizationEngine._make_scorer(
            strategy_name, df_candles, symbol, timeframe, initial_capital
        )

        if method == "TPE":
            candidates = ParameterOptimizationEngine._run_tpe(
                combinations, scorer, max_evaluations, seed
            )
        else:
            candidates = [c for c in (scorer(p) for p in combinations) if c is not None]

        if not candidates:
            return OptimizationResult(
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                method=method,
                total_evaluations=0,
                best_candidate=None,
                top_candidates=[],
                overfitting_warning=False,
                recommendation=(
                    f"Strategy '{strategy_name}' exposes no tunable parameters, "
                    "so there was nothing to search."
                ),
            )

        candidates.sort(key=lambda c: c.sharpe_ratio, reverse=True)
        top = candidates[:10]
        best = top[0]

        overfit, recommendation = ParameterOptimizationEngine._assess(candidates, best)

        return OptimizationResult(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            method=method,
            total_evaluations=len(candidates),
            best_candidate=best,
            top_candidates=top,
            overfitting_warning=overfit,
            recommendation=recommendation,
        )

    @staticmethod
    def _make_scorer(
        strategy_name: str,
        df_candles: pd.DataFrame,
        symbol: str,
        timeframe: str,
        initial_capital: float,
    ) -> Callable[[dict[str, Any]], OptimizationCandidate | None]:
        """Build a function that backtests one parameter set."""

        def score(params: dict[str, Any]) -> OptimizationCandidate | None:
            try:
                strategy = StrategyRegistry.build(strategy_name, **params)
            except KeyError:
                return None

            # Score this exact parameterization, not the registry default.
            engine = BacktestEngine(
                BacktestRequest(
                    symbol=symbol,
                    timeframe=timeframe,
                    strategy_name=strategy_name,
                    initial_capital=initial_capital,
                ),
                strategy=strategy,
            )
            result = engine.run(df_candles)
            return OptimizationCandidate(
                params=params,
                sharpe_ratio=result.metrics.sharpe_ratio,
                sortino_ratio=result.metrics.sortino_ratio,
                total_return_pct=result.metrics.total_return_pct,
                max_drawdown_pct=result.metrics.max_drawdown_pct,
                profit_factor=result.metrics.profit_factor,
                total_trades=result.metrics.total_trades,
            )

        return score

    @staticmethod
    def _run_tpe(
        combinations: list[dict[str, Any]],
        scorer: Callable[[dict[str, Any]], OptimizationCandidate | None],
        max_evaluations: int,
        seed: int,
    ) -> list[OptimizationCandidate]:
        """Tree-structured Parzen Estimator over a discrete parameter space.

        Sequential model-based optimization, the same family Optuna's default
        sampler belongs to. After a random warm-up it splits observed trials
        into a "good" quantile and the rest, estimates the probability of each
        candidate value under both, and evaluates the untried point maximizing
        l(x)/g(x).

        Implemented with plain arithmetic over a discrete grid rather than a
        Gaussian process, so it needs no extra dependency and is exact for the
        finite spaces this registry defines. It is genuinely adaptive: it will
        not evaluate the whole grid unless the budget allows.
        """
        if not combinations:
            return []

        rng = random.Random(seed)
        budget = min(max_evaluations, len(combinations))
        # Enough random trials to have something to model before exploiting.
        warmup = max(TPE_MIN_WARMUP, int(budget * TPE_WARMUP_FRACTION))

        remaining = combinations[:]
        rng.shuffle(remaining)

        evaluated: list[tuple[dict[str, Any], OptimizationCandidate]] = []
        while remaining and len(evaluated) < budget:
            if len(evaluated) < warmup:
                params = remaining.pop()
            else:
                params = ParameterOptimizationEngine._tpe_select(evaluated, remaining, rng)
                remaining.remove(params)

            candidate = scorer(params)
            if candidate is None:
                # Strategy takes no parameters; nothing to search.
                break
            evaluated.append((params, candidate))

        return [candidate for _, candidate in evaluated]

    @staticmethod
    def _tpe_select(
        evaluated: list[tuple[dict[str, Any], OptimizationCandidate]],
        remaining: list[dict[str, Any]],
        rng: random.Random,
    ) -> dict[str, Any]:
        """Pick the untried point with the highest good/bad density ratio."""
        ranked = sorted(evaluated, key=lambda pair: pair[1].sharpe_ratio, reverse=True)
        split = max(1, int(len(ranked) * TPE_GOOD_QUANTILE))
        good = [params for params, _ in ranked[:split]]
        bad = [params for params, _ in ranked[split:]] or [params for params, _ in ranked]

        def density(pool: list[dict[str, Any]], key: str, value: Any) -> float:
            # Laplace smoothing keeps an unseen value from producing a zero (or
            # infinite) ratio purely because the warm-up happened to miss it.
            hits = sum(1 for p in pool if p.get(key) == value)
            return (hits + 1.0) / (len(pool) + 2.0)

        best_params = remaining[0]
        best_score = -math.inf
        for params in remaining:
            score = 0.0
            for key, value in params.items():
                score += math.log(density(good, key, value)) - math.log(density(bad, key, value))
            # Tiny jitter breaks ties without biasing toward list order.
            score += rng.random() * 1e-9
            if score > best_score:
                best_score = score
                best_params = params
        return best_params

    @staticmethod
    def _expand(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
        """Turn a parameter grid into a list of concrete parameter sets."""
        if not grid:
            return []
        keys = list(grid.keys())
        return [dict(zip(keys, values, strict=True)) for values in itertools.product(*grid.values())]

    @staticmethod
    def _assess(
        candidates: list[OptimizationCandidate],
        best: OptimizationCandidate,
    ) -> tuple[bool, str]:
        """Judge whether the winner looks like a fitting artefact.

        A best result that towers over the rest of the space is usually a lucky
        cell rather than a robust region, and a winner with very few trades has
        no statistical support regardless of its Sharpe.
        """
        if best.total_trades < 10:
            return True, (
                f"Best parameters produced only {best.total_trades} trades. "
                "That is too few to distinguish skill from noise."
            )

        if len(candidates) < 3:
            return False, (
                f"Only {len(candidates)} parameter sets were evaluated; "
                "the search space is too small to judge robustness."
            )

        others = [c.sharpe_ratio for c in candidates[1:]]
        median_other = sorted(others)[len(others) // 2]
        if median_other > 0 and best.sharpe_ratio > median_other * 2.5:
            return True, (
                f"Best Sharpe ({best.sharpe_ratio}) is far above the median of the "
                f"rest of the grid ({median_other}). This looks like an isolated "
                "peak rather than a stable region; validate with walk-forward."
            )

        return False, (
            f"Best Sharpe ({best.sharpe_ratio}) is consistent with neighbouring "
            f"parameter sets across {len(candidates)} evaluations. Confirm with "
            "walk-forward before trusting it."
        )
