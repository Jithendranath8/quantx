"""
QuantX — Monte Carlo Simulation Engine.

Resamples historical trade PnLs to estimate:
- Final equity distribution
- Max drawdown distribution
- Probability of ruin
- 95th percentile worst-case drawdown
- Expected longest losing streak
"""

import numpy as np
from pydantic import BaseModel

MAX_SIMULATIONS = 50_000
RUIN_THRESHOLD_PCT = 0.5  # Equity at or below 50% of starting capital.


class MonteCarloSummary(BaseModel):
    """Distributional summary of the simulated equity paths."""

    num_simulations: int
    num_trades_per_path: int
    initial_capital: float
    mean_final_equity: float
    median_final_equity: float
    probability_of_ruin_pct: float
    worst_case_drawdown_95_pct: float
    median_max_drawdown_pct: float
    expected_longest_losing_streak: int
    percentile_5_equity: float
    percentile_95_equity: float


class MonteCarloEngine:
    """Simulates randomized equity curve paths by bootstrap resampling."""

    @staticmethod
    def run_simulation(
        trades_pnl: list[float],
        initial_capital: float = 10_000.0,
        num_simulations: int = 1000,
        seed: int = 42,
    ) -> MonteCarloSummary:
        """Run bootstrap resampling over historical trade PnLs.

        Args:
            trades_pnl: Historical trade PnLs to resample from.
            initial_capital: Starting capital for each path.
            num_simulations: Number of paths to simulate.
            seed: Fixed for reproducibility; a research result that changes on
                every call cannot be compared across runs.
        """
        num_simulations = max(1, min(num_simulations, MAX_SIMULATIONS))

        if not trades_pnl:
            return MonteCarloSummary(
                num_simulations=0,
                num_trades_per_path=0,
                initial_capital=initial_capital,
                mean_final_equity=initial_capital,
                median_final_equity=initial_capital,
                probability_of_ruin_pct=0.0,
                worst_case_drawdown_95_pct=0.0,
                median_max_drawdown_pct=0.0,
                expected_longest_losing_streak=0,
                percentile_5_equity=initial_capital,
                percentile_95_equity=initial_capital,
            )

        rng = np.random.default_rng(seed)
        pnls = np.asarray(trades_pnl, dtype=float)
        n_trades = len(pnls)

        # Vectorized: draw every path at once instead of looping in Python.
        draws = rng.choice(pnls, size=(num_simulations, n_trades), replace=True)
        equity_paths = np.hstack(
            [np.full((num_simulations, 1), initial_capital), initial_capital + np.cumsum(draws, axis=1)]
        )

        final_equities = equity_paths[:, -1]

        running_peak = np.maximum.accumulate(equity_paths, axis=1)
        # Guard against a peak of zero, which a ruinous path can reach.
        safe_peak = np.where(running_peak == 0, np.nan, running_peak)
        drawdowns = (running_peak - equity_paths) / safe_peak
        max_drawdowns = np.nan_to_num(np.nanmax(drawdowns, axis=1)) * 100

        ruin_count = int(np.sum(final_equities <= initial_capital * RUIN_THRESHOLD_PCT))

        return MonteCarloSummary(
            num_simulations=num_simulations,
            num_trades_per_path=n_trades,
            initial_capital=initial_capital,
            mean_final_equity=round(float(np.mean(final_equities)), 2),
            median_final_equity=round(float(np.median(final_equities)), 2),
            probability_of_ruin_pct=round(ruin_count / num_simulations * 100, 2),
            worst_case_drawdown_95_pct=round(float(np.percentile(max_drawdowns, 95)), 2),
            median_max_drawdown_pct=round(float(np.median(max_drawdowns)), 2),
            expected_longest_losing_streak=MonteCarloEngine._expected_losing_streak(draws),
            percentile_5_equity=round(float(np.percentile(final_equities, 5)), 2),
            percentile_95_equity=round(float(np.percentile(final_equities, 95)), 2),
        )

    @staticmethod
    def _expected_losing_streak(draws: np.ndarray) -> int:
        """Mean longest run of consecutive losses across the simulated paths.

        Computed from the simulation rather than returned as a constant.
        """
        losses = draws <= 0
        longest = np.zeros(losses.shape[0], dtype=int)
        current = np.zeros(losses.shape[0], dtype=int)
        for column in range(losses.shape[1]):
            current = np.where(losses[:, column], current + 1, 0)
            longest = np.maximum(longest, current)
        return round(float(np.mean(longest)))
