"""
QuantX — Comprehensive Technical Indicators Suite.

Implements EMA, SMA, RSI, MACD, Bollinger Bands, ATR, ADX, VWAP, Volume Profile,
Stochastic, OBV, and Ichimoku Cloud using vectorized NumPy/Pandas.
"""

import numpy as np
import pandas as pd

from app.engines.indicators.base import BaseIndicator


def _true_range(df: pd.DataFrame) -> pd.Series:
    """True Range: the greatest of H-L, |H-prevC| and |L-prevC|."""
    previous_close = df["close"].shift()
    return pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


class SMA(BaseIndicator):
    """Simple Moving Average."""
    name = "sma"

    def __init__(self, period: int = 20) -> None:
        self.period = period

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        col = f"sma_{self.period}"
        df[col] = df["close"].rolling(window=self.period).mean()
        return df


class EMA(BaseIndicator):
    """Exponential Moving Average."""
    name = "ema"

    def __init__(self, period: int = 20) -> None:
        self.period = period

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        col = f"ema_{self.period}"
        df[col] = df["close"].ewm(span=self.period, adjust=False).mean()
        return df


class RSI(BaseIndicator):
    """Relative Strength Index (Wilder).

    Uses Wilder's smoothing, which is the definition every charting platform
    implements. A simple rolling mean of gains and losses produces visibly
    different values, so signals would not reproduce anywhere else.
    """

    name = "rsi"

    def __init__(self, period: int = 14) -> None:
        self.period = period

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        delta = df["close"].diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)

        # Wilder's smoothing is an EMA with alpha = 1/period.
        avg_gain = gain.ewm(alpha=1 / self.period, min_periods=self.period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / self.period, min_periods=self.period, adjust=False).mean()

        # avg_loss == 0 with gains divides to +inf, which resolves to 100
        # naturally. Only the fully flat case (no gains AND no losses) is
        # genuinely undefined and is reported as the neutral 50.
        #
        # The previous implementation did loss.replace(0, np.nan), so a
        # strictly rising series -- exactly the case RSI should report as
        # maximally overbought -- came back NaN, and RSI strategies never
        # fired during a strong trend. Warm-up rows stay NaN, as they should.
        rsi = 100 - (100 / (1 + avg_gain / avg_loss))
        rsi = rsi.mask((avg_loss == 0) & (avg_gain == 0), 50.0)

        df[f"rsi_{self.period}"] = rsi
        return df


class MACD(BaseIndicator):
    """Moving Average Convergence Divergence."""
    name = "macd"

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        ema_fast = df["close"].ewm(span=self.fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=self.slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.signal, adjust=False).mean()
        histogram = macd_line - signal_line

        df["macd_line"] = macd_line
        df["macd_signal"] = signal_line
        df["macd_histogram"] = histogram
        return df


class BollingerBands(BaseIndicator):
    """Bollinger Bands."""
    name = "bollinger"

    def __init__(self, period: int = 20, std_dev: float = 2.0) -> None:
        self.period = period
        self.std_dev = std_dev

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        middle = df["close"].rolling(window=self.period).mean()
        std = df["close"].rolling(window=self.period).std()
        upper = middle + (std * self.std_dev)
        lower = middle - (std * self.std_dev)

        df["bb_middle"] = middle
        df["bb_upper"] = upper
        df["bb_lower"] = lower
        df["bb_bandwidth"] = (upper - lower) / middle
        df["bb_percent_b"] = (df["close"] - lower) / (upper - lower)
        return df


class ATR(BaseIndicator):
    """Average True Range."""
    name = "atr"

    def __init__(self, period: int = 14) -> None:
        self.period = period

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        tr = _true_range(df)
        # Wilder smoothing, matching the standard ATR definition.
        df[f"atr_{self.period}"] = tr.ewm(
            alpha=1 / self.period, min_periods=self.period, adjust=False
        ).mean()
        return df


class ADX(BaseIndicator):
    """Average Directional Index."""
    name = "adx"

    def __init__(self, period: int = 14) -> None:
        self.period = period

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        up_move = df["high"].diff()
        down_move = -df["low"].diff()

        plus_dm = pd.Series(
            np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index
        )
        minus_dm = pd.Series(
            np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index
        )

        alpha = 1 / self.period
        # Wilder smoothing throughout, and the raw pd.Series construction below
        # now carries df.index -- previously plus_dm/minus_dm were built with a
        # fresh RangeIndex, so dividing by atr silently misaligned on any frame
        # whose index was not 0..n-1.
        tr = _true_range(df)
        atr = tr.ewm(alpha=alpha, min_periods=self.period, adjust=False).mean()

        plus_di = 100 * plus_dm.ewm(alpha=alpha, min_periods=self.period, adjust=False).mean() / atr
        minus_di = 100 * minus_dm.ewm(alpha=alpha, min_periods=self.period, adjust=False).mean() / atr

        di_sum = (plus_di + minus_di).replace(0, np.nan)
        dx = 100 * (plus_di - minus_di).abs() / di_sum
        adx = dx.ewm(alpha=alpha, min_periods=self.period, adjust=False).mean()

        df[f"adx_{self.period}"] = adx
        df[f"plus_di_{self.period}"] = plus_di
        df[f"minus_di_{self.period}"] = minus_di
        return df


class VWAP(BaseIndicator):
    """Volume Weighted Average Price."""
    name = "vwap"

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        df["vwap"] = (typical_price * df["volume"]).cumsum() / df["volume"].cumsum()
        return df


class Stochastic(BaseIndicator):
    """Stochastic Oscillator."""
    name = "stochastic"

    def __init__(self, k_period: int = 14, d_period: int = 3) -> None:
        self.k_period = k_period
        self.d_period = d_period

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        lowest_low = df["low"].rolling(window=self.k_period).min()
        highest_high = df["high"].rolling(window=self.k_period).max()

        k = 100 * ((df["close"] - lowest_low) / (highest_high - lowest_low).replace(0, np.nan))
        d = k.rolling(window=self.d_period).mean()

        df["stoch_k"] = k
        df["stoch_d"] = d
        return df


class OBV(BaseIndicator):
    """On-Balance Volume."""
    name = "obv"

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        direction = np.where(df["close"] > df["close"].shift(), 1, np.where(df["close"] < df["close"].shift(), -1, 0))
        df["obv"] = (df["volume"] * direction).fillna(0).cumsum()
        return df


class Ichimoku(BaseIndicator):
    """Ichimoku Kinko Hyo Cloud."""
    name = "ichimoku"

    def __init__(self, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52) -> None:
        self.tenkan = tenkan
        self.kijun = kijun
        self.senkou_b = senkou_b

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        tenkan_sen = (df["high"].rolling(window=self.tenkan).max() + df["low"].rolling(window=self.tenkan).min()) / 2
        kijun_sen = (df["high"].rolling(window=self.kijun).max() + df["low"].rolling(window=self.kijun).min()) / 2
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(self.kijun)
        senkou_span_b = ((df["high"].rolling(window=self.senkou_b).max() + df["low"].rolling(window=self.senkou_b).min()) / 2).shift(self.kijun)
        chikou_span = df["close"].shift(-self.kijun)

        df["ichimoku_tenkan"] = tenkan_sen
        df["ichimoku_kijun"] = kijun_sen
        df["ichimoku_span_a"] = senkou_span_a
        df["ichimoku_span_b"] = senkou_span_b
        df["ichimoku_chikou"] = chikou_span
        return df
