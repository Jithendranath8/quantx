"""
QuantX — Unit Tests for Technical Indicator Calculators.
"""

import pandas as pd
import pytest

from app.engines.indicators.calculators import MACD, RSI, SMA
from app.engines.indicators.registry import IndicatorRegistry


@pytest.fixture
def sample_ohlcv_df() -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    dates = pd.date_range("2026-01-01", periods=100, freq="1h")
    data = {
        "timestamp": dates,
        "open": [100 + i * 0.5 for i in range(100)],
        "high": [102 + i * 0.5 for i in range(100)],
        "low": [99 + i * 0.5 for i in range(100)],
        "close": [101 + i * 0.5 for i in range(100)],
        "volume": [1000 + i * 10 for i in range(100)],
    }
    return pd.DataFrame(data)


@pytest.mark.unit
class TestIndicators:
    """Unit tests for individual indicator calculations."""

    def test_sma(self, sample_ohlcv_df: pd.DataFrame) -> None:
        sma = SMA(period=10)
        res = sma.calculate(sample_ohlcv_df)
        assert "sma_10" in res.columns
        assert pd.notna(res["sma_10"].iloc[-1])

    def test_rsi(self, sample_ohlcv_df: pd.DataFrame) -> None:
        rsi = RSI(period=14)
        res = rsi.calculate(sample_ohlcv_df)
        assert "rsi_14" in res.columns
        # Upward trending data should have high RSI
        assert res["rsi_14"].iloc[-1] > 50

    def test_macd(self, sample_ohlcv_df: pd.DataFrame) -> None:
        macd = MACD()
        res = macd.calculate(sample_ohlcv_df)
        assert "macd_line" in res.columns
        assert "macd_signal" in res.columns
        assert "macd_histogram" in res.columns

    def test_registry_compute_all(self, sample_ohlcv_df: pd.DataFrame) -> None:
        registry = IndicatorRegistry()
        res = registry.compute_all(sample_ohlcv_df)
        assert "ema_200" in res.columns
        assert "rsi_14" in res.columns
        assert "bb_upper" in res.columns
