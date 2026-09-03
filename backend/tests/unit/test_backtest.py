"""
QuantX — Unit Tests for Backtest Engine & Performance Metrics.
"""

import pandas as pd
import pytest

from app.engines.backtest.engine import BacktestEngine
from app.engines.backtest.metrics import PerformanceMetricsCalculator
from app.schemas.backtest import BacktestRequest


@pytest.fixture
def synthetic_candles() -> pd.DataFrame:
    """Generate 100 synthetic candles for backtesting."""
    dates = pd.date_range("2026-01-01", periods=100, freq="1h")
    data = {
        "timestamp": dates,
        "open": [100 + (i % 10) for i in range(100)],
        "high": [105 + (i % 10) for i in range(100)],
        "low": [98 + (i % 10) for i in range(100)],
        "close": [102 + (i % 10) for i in range(100)],
        "volume": [1000 for _ in range(100)],
    }
    return pd.DataFrame(data)


@pytest.mark.unit
class TestBacktestEngine:
    """Unit tests for backtesting simulation and metric calculations."""

    def test_metrics_calculator_empty(self) -> None:
        """Empty trade list should return zeroed metrics."""
        m = PerformanceMetricsCalculator.calculate(10000.0, [], pd.Series())
        assert m.net_profit_usd == 0.0
        assert m.sharpe_ratio == 0.0
        assert m.win_rate_pct == 0.0

    def test_backtest_engine_run(self, synthetic_candles: pd.DataFrame) -> None:
        """Engine run should return populated BacktestResult."""
        req = BacktestRequest(
            symbol="BTCUSDT",
            timeframe="1h",
            strategy_name="ema_crossover",
            initial_capital=10000.0,
        )
        engine = BacktestEngine(req)
        res = engine.run(synthetic_candles)

        assert res.symbol == "BTCUSDT"
        assert res.initial_capital == 10000.0
        assert res.metrics is not None
