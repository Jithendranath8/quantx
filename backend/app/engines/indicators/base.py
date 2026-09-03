"""
QuantX — Indicator Engine Base Class.

Provides abstract interface for technical indicator calculators.
Uses pandas DataFrames for high-performance vectorized operations.
"""

from abc import ABC, abstractmethod

import pandas as pd


class BaseIndicator(ABC):
    """Abstract Base Class for technical indicator implementations."""

    name: str = "base_indicator"

    @abstractmethod
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicator on input OHLCV DataFrame.

        Args:
            df: DataFrame containing 'open', 'high', 'low', 'close', 'volume' columns.

        Returns:
            DataFrame with indicator columns appended.
        """
        pass
