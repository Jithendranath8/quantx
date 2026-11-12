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
# Ceiling on simulations x trades for one run. At roughly 40 bytes per cell an
# uncapped request reached gigabytes; this keeps the whole run to a bounded
# amount of CPU, and CHUNK_CELLS keeps its peak memory near 100 MB.
MAX_TOTAL_CELLS = 20_000_000
CHUNK_CELLS = 2_000_000
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

        # Bound the work by simulations x trades, not by simulations alone. The
        # simulation count was capped but the product was not, so a strategy
        # with many trades turned one request into gigabytes of arrays in the
        # shared API process. Above the budget the simulation count is reduced
        # and the summary reports the number actually run.
        num_simulations = max(1, min(num_simulations, MAX_TOTAL_CELLS // n_trades))

        final_equities = np.empty(num_simulations, dtype=float)
        max_drawdowns = np.empty(num_simulations, dtype=float)
        longest_streaks = np.empty(num_simulations, dtype=int)

        # Paths are simulated in fixed-size chunks and only three numbers per
        # path are kept, so peak memory is set by the chunk, not the request.
        chunk_size = max(1, CHUNK_CELLS // n_trades)
        for start in range(0, num_simulations, chunk_size):
            stop = min(start + chunk_size, num_simulations)
            rows = stop - start
            draws = rng.choice(pnls, size=(rows, n_trades), replace=True)
            equity_paths = np.hstack(
                [np.full((rows, 1), initial_capital), initial_capital + np.cumsum(draws, axis=1)]
            )
            final_equities[start:stop] = equity_paths[:, -1]

            running_peak = np.maximum.accumulate(equity_paths, axis=1)
            # Guard against a peak of zero, which a ruinous path can reach.
            safe_peak = np.where(running_peak == 0, np.nan, running_peak)
            drawdowns = (running_peak - equity_paths) / safe_peak
            max_drawdowns[start:stop] = np.nan_to_num(np.nanmax(drawdowns, axis=1)) * 100
            longest_streaks[start:stop] = MonteCarloEngine._longest_losing_streaks(draws)

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
            expected_longest_losing_streak=round(float(np.mean(longest_streaks))),
            percentile_5_equity=round(float(np.percentile(final_equities, 5)), 2),
            percentile_95_equity=round(float(np.percentile(final_equities, 95)), 2),
        )

    @staticmethod
    def _longest_losing_streaks(draws: np.ndarray) -> np.ndarray:
        """Longest run of consecutive losses on each simulated path."""
        losses = draws <= 0
        longest = np.zeros(losses.shape[0], dtype=int)
        current = np.zeros(losses.shape[0], dtype=int)
        for column in range(losses.shape[1]):
            current = np.where(losses[:, column], current + 1, 0)
            longest = np.maximum(longest, current)
        return longest

    @staticmethod
    def _expected_losing_streak(draws: np.ndarray) -> int:
        """Mean longest run of consecutive losses across the simulated paths.

        Computed from the simulation rather than returned as a constant.
        """
        return round(float(np.mean(MonteCarloEngine._longest_losing_streaks(draws))))
