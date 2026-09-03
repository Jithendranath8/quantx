"""
QuantX — Indicator Registry & Execution Engine.

Aggregates indicator calculators and applies them to OHLCV DataFrames.
"""

from typing import Any

import pandas as pd

from app.engines.indicators.calculators import (
    ADX,
    ATR,
    EMA,
    MACD,
    OBV,
    RSI,
    SMA,
    VWAP,
    BollingerBands,
    Ichimoku,
    Stochastic,
)


class IndicatorRegistry:
    """Registry managing available technical indicator calculators."""

    def __init__(self) -> None:
        self._default_indicators = [
            SMA(20),
            EMA(9),
            EMA(21),
            EMA(50),
            EMA(200),
            RSI(14),
            MACD(12, 26, 9),
            BollingerBands(20, 2.0),
            ATR(14),
            ADX(14),
            VWAP(),
            Stochastic(14, 3),
            OBV(),
            Ichimoku(9, 26, 52),
        ]

    def compute_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply all default technical indicators to an OHLCV DataFrame."""
        if df.empty:
            return df

        result_df = df.copy()
        for indicator in self._default_indicators:
            result_df = indicator.calculate(result_df)

        return result_df

    def compute_indicator_summary(self, df: pd.DataFrame) -> dict[str, Any]:
        """Extract latest calculated indicator values as a dictionary."""
        df_computed = self.compute_all(df)
        if df_computed.empty:
            return {}

        latest = df_computed.iloc[-1].to_dict()
        summary = {}

        for k, v in latest.items():
            if pd.isna(v):
                summary[k] = None
            elif isinstance(v, (int, float, str, bool)):
                summary[k] = float(v) if isinstance(v, (int, float)) else v
            else:
                summary[k] = str(v)

        return summary
