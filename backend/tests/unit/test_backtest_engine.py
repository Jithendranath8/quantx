"""
QuantX — Unit Tests for the backtesting engine and its metrics.
"""

import math

import pandas as pd
import pytest

from app.engines.backtest.engine import WARMUP_BARS, BacktestEngine
from app.engines.backtest.metrics import PerformanceMetricsCalculator, periods_per_year
from app.engines.strategy.base import BaseStrategy, Signal
from app.schemas.backtest import BacktestRequest


def make_frame(n: int = 300) -> pd.DataFrame:
    """A trending series with a cycle, so crossovers actually occur."""
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


class AlwaysBuy(BaseStrategy):
    """Enters long on the first opportunity and never exits by signal."""

    name = "always_buy"
    description = "test strategy"

    def generate_signal(self, symbol: str, timeframe: str, df: pd.DataFrame) -> Signal:
        close = float(df.iloc[-1]["close"])
        return Signal(
            action="BUY",
            symbol=symbol,
            timeframe=timeframe,
            confidence=1.0,
            reasoning="test",
            entry_price=close,
            stop_loss=close * 0.90,
            take_profit=close * 1.10,
        )


class WindowSpy(BaseStrategy):
    """Records how many rows it is handed each bar."""

    name = "window_spy"
    description = "test strategy"
    lookback = 2

    def __init__(self) -> None:
        self.window_sizes: list[int] = []

    def generate_signal(self, symbol: str, timeframe: str, df: pd.DataFrame) -> Signal:
        self.window_sizes.append(len(df))
        return Signal(
            action="WAIT", symbol=symbol, timeframe=timeframe, confidence=0.0, reasoning="test"
        )


def request(**kwargs: object) -> BacktestRequest:
    """Build a backtest request with test defaults."""
    return BacktestRequest(
        **{
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "strategy_name": "ema_crossover",
            "initial_capital": 10_000.0,
            **kwargs,
        }
    )


@pytest.mark.unit
class TestBacktestEngine:
    """Simulation mechanics."""

    def test_insufficient_data_returns_empty_result(self) -> None:
        """Too few bars produces an empty result, not invented performance."""
        result = BacktestEngine(request()).run(make_frame(10))
        assert result.equity_curve == []
        assert result.metrics.total_trades == 0
        assert result.final_equity == 10_000.0

    def test_unknown_strategy_raises(self) -> None:
        """An unregistered strategy is an error, not a silent no-op."""
        with pytest.raises(ValueError, match="not found"):
            BacktestEngine(request(strategy_name="does_not_exist")).run(make_frame())

    def test_strategy_receives_only_its_declared_lookback(self) -> None:
        """The engine hands over a bounded window, not the whole history.

        Passing df.iloc[:i+1] every bar copies a linearly growing frame, making
        a run O(n^2): ~1000 candles meant ~500,000 row-copies per backtest.
        """
        spy = WindowSpy()
        BacktestEngine(request(strategy_name="window_spy"), strategy=spy).run(make_frame(300))

        assert spy.window_sizes, "strategy was never called"
        assert max(spy.window_sizes) <= spy.lookback
        # And the window never grows with the bar index.
        assert len(set(spy.window_sizes)) == 1

    def test_stop_loss_is_honoured(self) -> None:
        """A position is closed when the bar's low reaches the stop."""
        frame = make_frame(120)
        # Crash the tail so any long position must stop out.
        frame.loc[100:, "low"] = 100.0
        frame.loc[100:, "close"] = 200.0

        result = BacktestEngine(request(strategy_name="always_buy"), strategy=AlwaysBuy()).run(frame)
        reasons = {t["reason"] for t in result.trades}
        assert "Stop Loss" in reasons

    def test_open_position_is_closed_at_end_of_data(self) -> None:
        """Final equity reflects a realizable number, not a paper position."""
        result = BacktestEngine(request(strategy_name="always_buy"), strategy=AlwaysBuy()).run(
            make_frame(200)
        )
        assert result.trades
        assert result.metrics.total_trades == len(result.trades)

    def test_fees_are_charged_on_both_sides(self) -> None:
        """Every closed trade records the entry and exit fee."""
        result = BacktestEngine(
            request(strategy_name="always_buy", fee_rate=0.001), strategy=AlwaysBuy()
        ).run(make_frame(200))
        assert all(t["fee"] > 0 for t in result.trades)

    def test_equity_curve_length_matches_traded_bars(self) -> None:
        """One equity point per simulated bar after warm-up."""
        frame = make_frame(200)
        result = BacktestEngine(request()).run(frame)
        assert len(result.equity_curve) == len(frame) - WARMUP_BARS


@pytest.mark.unit
class TestMetrics:
    """Performance metric calculation."""

    def test_empty_inputs_are_zeroed(self) -> None:
        """No trades yields zeros rather than NaN."""
        metrics = PerformanceMetricsCalculator.calculate(10_000.0, [], pd.Series(dtype=float))
        assert metrics.total_trades == 0
        assert metrics.sharpe_ratio == 0.0

    def test_annualization_follows_the_timeframe(self) -> None:
        """Sharpe scales with bar size.

        Annualizing a 1m curve with the hourly factor understates Sharpe by
        about 7.7x, so the timeframe has to feed into the calculation.
        """
        assert periods_per_year("1m") == 525_600
        assert periods_per_year("1h") == 8_760
        assert periods_per_year("1d") == 365
        assert periods_per_year("nonsense") == 8_760

        equity = pd.Series([10_000 * (1.001**i) for i in range(200)])
        trades = [{"pnl": 10.0}, {"pnl": -5.0}]
        hourly = PerformanceMetricsCalculator.calculate(10_000.0, trades, equity, "1h")
        minutely = PerformanceMetricsCalculator.calculate(10_000.0, trades, equity, "1m")
        assert minutely.sharpe_ratio > hourly.sharpe_ratio

    def test_win_and_loss_counts(self) -> None:
        """Wins and losses are counted from realized PnL."""
        equity = pd.Series([10_000.0, 10_050.0, 10_020.0])
        trades = [{"pnl": 50.0}, {"pnl": -30.0}, {"pnl": 20.0}]
        metrics = PerformanceMetricsCalculator.calculate(10_000.0, trades, equity, "1h")
        assert metrics.total_trades == 3
        assert metrics.winning_trades == 2
        assert metrics.losing_trades == 1
        assert metrics.win_rate_pct == pytest.approx(66.67, abs=0.01)
