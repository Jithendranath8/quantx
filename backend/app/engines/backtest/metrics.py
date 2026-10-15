"""
QuantX — Backtesting Performance Metrics Calculator.

Computes Sharpe Ratio, Sortino Ratio, Max Drawdown %, Win Rate %, and Profit Factor.
"""

from typing import Any

import numpy as np
import pandas as pd

from app.schemas.backtest import BacktestMetrics

# Bars per year for each supported timeframe. Annualizing a 1m equity curve
# with the hourly factor understates Sharpe by ~7.7x, so the ratio must be
# scaled by the timeframe the backtest actually ran on.
PERIODS_PER_YEAR: dict[str, float] = {
    "1m": 525_600,
    "3m": 175_200,
    "5m": 105_120,
    "15m": 35_040,
    "30m": 17_520,
    "1h": 8_760,
    "2h": 4_380,
    "4h": 2_190,
    "6h": 1_460,
    "8h": 1_095,
    "12h": 730,
    "1d": 365,
    "3d": 121.67,
    "1w": 52,
}
DEFAULT_PERIODS_PER_YEAR = 8_760.0


def periods_per_year(timeframe: str) -> float:
    """Bars per year for a timeframe, defaulting to hourly when unknown."""
    return PERIODS_PER_YEAR.get(timeframe, DEFAULT_PERIODS_PER_YEAR)


class PerformanceMetricsCalculator:
    """Calculates institutional backtesting performance metrics from trade logs and equity curve."""

    @staticmethod
    def calculate(
        initial_capital: float,
        trades: list[dict[str, Any]],
        equity_series: pd.Series,
        timeframe: str = "1h",
    ) -> BacktestMetrics:
        """Calculate complete performance metrics.

        Args:
            initial_capital: Starting capital USD.
            trades: Trade dictionaries containing at least 'pnl'.
            equity_series: Series of equity values, one per bar.
            timeframe: Bar size, used to annualize Sharpe and Sortino correctly.
        """
        if not trades or equity_series.empty:
            return BacktestMetrics(
                total_return_pct=0.0,
                net_profit_usd=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                max_drawdown_pct=0.0,
                win_rate_pct=0.0,
                profit_factor=0.0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                avg_trade_pnl_usd=0.0,
            )

        final_equity = float(equity_series.iloc[-1])
        net_profit_usd = final_equity - initial_capital
        total_return_pct = (net_profit_usd / initial_capital) * 100

        # Drawdown calculation
        rolling_max = equity_series.cummax()
        drawdown = (equity_series - rolling_max) / rolling_max
        max_drawdown_pct = abs(float(drawdown.min())) * 100 if not drawdown.empty else 0.0

        # Returns analysis for Sharpe & Sortino
        pct_changes = equity_series.pct_change().dropna()
        mean_ret = float(pct_changes.mean())
        std_ret = float(pct_changes.std())

        # Annualization factor derived from the actual bar size.
        annual_factor = float(np.sqrt(periods_per_year(timeframe)))
        sharpe_ratio = (mean_ret / std_ret * annual_factor) if std_ret > 0 else 0.0

        # Downside Deviation for Sortino
        downside_returns = pct_changes[pct_changes < 0]
        downside_std = float(downside_returns.std())
        sortino_ratio = (mean_ret / downside_std * annual_factor) if downside_std > 0 else 0.0

        # Trade metrics
        total_trades = len(trades)
        pnls = [t["pnl"] for t in trades]
        winning_trades = sum(1 for p in pnls if p > 0)
        losing_trades = sum(1 for p in pnls if p <= 0)

        win_rate_pct = (winning_trades / total_trades) * 100 if total_trades > 0 else 0.0

        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)

        avg_trade_pnl_usd = float(np.mean(pnls)) if pnls else 0.0

        return BacktestMetrics(
            total_return_pct=round(total_return_pct, 2),
            net_profit_usd=round(net_profit_usd, 2),
            sharpe_ratio=round(sharpe_ratio, 2),
            sortino_ratio=round(sortino_ratio, 2),
            max_drawdown_pct=round(max_drawdown_pct, 2),
            win_rate_pct=round(win_rate_pct, 2),
            profit_factor=round(profit_factor, 2),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_trade_pnl_usd=round(avg_trade_pnl_usd, 2),
        )
