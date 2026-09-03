"""
QuantX — Unit Tests for Quantitative Strategies.
"""

import pandas as pd
import pytest

from app.engines.strategy.strategies import (
    EMACrossoverStrategy,
    MACDMomentumStrategy,
    RSIMeanReversionStrategy,
)


@pytest.fixture
def ohlcv_with_indicators() -> pd.DataFrame:
    """Generate OHLCV DataFrame with indicators."""
    df = pd.DataFrame(
        {
            "close": [100.0, 102.0, 105.0, 108.0, 110.0],
            "ema_9": [98.0, 99.0, 101.0, 104.0, 108.0],
            "ema_21": [99.0, 99.5, 100.0, 101.0, 103.0],
            "rsi_14": [25.0, 28.0, 45.0, 60.0, 75.0],
            "macd_histogram": [-0.5, -0.2, 0.1, 0.4, 0.8],
        }
    )
    return df


@pytest.mark.unit
class TestStrategies:
    """Unit tests for strategy signal generation logic."""

    def test_ema_crossover_buy(self, ohlcv_with_indicators: pd.DataFrame) -> None:
        strat = EMACrossoverStrategy()
        # Row 2 (index 1): ema_9 (99) <= ema_21 (99.5)
        # Row 3 (index 2): ema_9 (101) > ema_21 (100.0) -> Crossover!
        sub_df = ohlcv_with_indicators.iloc[:3]
        sig = strat.generate_signal("BTCUSDT", "1h", sub_df)

        assert sig.action == "BUY"
        assert sig.confidence > 0.8
        assert "Bullish crossover" in sig.reasoning

    def test_rsi_oversold_buy(self, ohlcv_with_indicators: pd.DataFrame) -> None:
        strat = RSIMeanReversionStrategy()
        # Row 1 (index 0): rsi = 25 (< 30) -> BUY
        sub_df = ohlcv_with_indicators.iloc[:1]
        sig = strat.generate_signal("BTCUSDT", "1h", sub_df)

        assert sig.action == "BUY"
        assert "oversold" in sig.reasoning

    def test_macd_momentum_buy(self, ohlcv_with_indicators: pd.DataFrame) -> None:
        strat = MACDMomentumStrategy()
        sig = strat.generate_signal("BTCUSDT", "1h", ohlcv_with_indicators)

        assert sig.action == "BUY"
        assert "Positive MACD momentum" in sig.reasoning
