"""
QuantX — Built-in Quantitative Strategies.

Implements EMA Crossover, RSI Mean Reversion, MACD Momentum,
Bollinger Band Breakout, and Multi-Timeframe Trend alignment strategies.
"""

import pandas as pd

from app.engines.strategy.base import BaseStrategy, Signal


class EMACrossoverStrategy(BaseStrategy):
    """EMA Fast x Slow Crossover Strategy."""

    name = "ema_crossover"
    description = "Generates signals based on fast EMA (9) crossing slow EMA (21)."

    def __init__(self, fast_col: str = "ema_9", slow_col: str = "ema_21") -> None:
        self.fast_col = fast_col
        self.slow_col = slow_col

    def generate_signal(self, symbol: str, timeframe: str, df: pd.DataFrame) -> Signal:
        if df.empty or len(df) < 2 or self.fast_col not in df.columns or self.slow_col not in df.columns:
            return Signal(
                action="WAIT",
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                reasoning="Insufficient data or missing EMA indicators",
            )

        prev = df.iloc[-2]
        curr = df.iloc[-1]

        # Bullish Crossover
        if prev[self.fast_col] <= prev[self.slow_col] and curr[self.fast_col] > curr[self.slow_col]:
            close_price = float(curr["close"])
            atr = float(curr.get("atr_14", close_price * 0.02))
            return Signal(
                action="BUY",
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.85,
                reasoning=f"Bullish crossover: {self.fast_col} ({curr[self.fast_col]:.2f}) crossed above {self.slow_col} ({curr[self.slow_col]:.2f})",
                entry_price=close_price,
                stop_loss=close_price - (atr * 1.5),
                take_profit=close_price + (atr * 3.0),
            )

        # Bearish Crossover
        if prev[self.fast_col] >= prev[self.slow_col] and curr[self.fast_col] < curr[self.slow_col]:
            close_price = float(curr["close"])
            atr = float(curr.get("atr_14", close_price * 0.02))
            return Signal(
                action="SELL",
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.85,
                reasoning=f"Bearish crossover: {self.fast_col} ({curr[self.fast_col]:.2f}) crossed below {self.slow_col} ({curr[self.slow_col]:.2f})",
                entry_price=close_price,
                stop_loss=close_price + (atr * 1.5),
                take_profit=close_price - (atr * 3.0),
            )

        return Signal(
            action="WAIT",
            symbol=symbol,
            timeframe=timeframe,
            confidence=0.5,
            reasoning="No crossover detected",
        )


class RSIMeanReversionStrategy(BaseStrategy):
    """RSI Oversold/Overbought Mean Reversion Strategy."""

    name = "rsi_mean_reversion"
    description = "Buys when RSI < 30 (oversold) and sells when RSI > 70 (overbought)."

    def __init__(self, oversold: float = 30.0, overbought: float = 70.0) -> None:
        self.oversold = oversold
        self.overbought = overbought

    def generate_signal(self, symbol: str, timeframe: str, df: pd.DataFrame) -> Signal:
        if df.empty or "rsi_14" not in df.columns:
            return Signal(action="WAIT", symbol=symbol, timeframe=timeframe, confidence=0.0, reasoning="Missing RSI indicator")

        curr = df.iloc[-1]
        rsi = float(curr["rsi_14"])
        close_price = float(curr["close"])

        if rsi < self.oversold:
            return Signal(
                action="BUY",
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.80,
                reasoning=f"RSI oversold at {rsi:.1f} (< {self.oversold})",
                entry_price=close_price,
                stop_loss=close_price * 0.97,
                take_profit=close_price * 1.05,
            )
        elif rsi > self.overbought:
            return Signal(
                action="SELL",
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.80,
                reasoning=f"RSI overbought at {rsi:.1f} (> {self.overbought})",
                entry_price=close_price,
                stop_loss=close_price * 1.03,
                take_profit=close_price * 0.95,
            )

        return Signal(action="WAIT", symbol=symbol, timeframe=timeframe, confidence=0.5, reasoning=f"RSI neutral at {rsi:.1f}")


class MACDMomentumStrategy(BaseStrategy):
    """MACD Histogram Momentum Strategy."""

    name = "macd_momentum"
    description = "Triggers signals on MACD histogram zero-line crossover and signal line divergence."

    def generate_signal(self, symbol: str, timeframe: str, df: pd.DataFrame) -> Signal:
        if df.empty or "macd_histogram" not in df.columns:
            return Signal(action="WAIT", symbol=symbol, timeframe=timeframe, confidence=0.0, reasoning="Missing MACD indicator")

        curr = df.iloc[-1]
        hist = float(curr["macd_histogram"])
        close_price = float(curr["close"])

        if hist > 0:
            return Signal(
                action="BUY",
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.75,
                reasoning=f"Positive MACD momentum: histogram = {hist:.4f}",
                entry_price=close_price,
            )
        elif hist < 0:
            return Signal(
                action="SELL",
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.75,
                reasoning=f"Negative MACD momentum: histogram = {hist:.4f}",
                entry_price=close_price,
            )

        return Signal(action="WAIT", symbol=symbol, timeframe=timeframe, confidence=0.5, reasoning="MACD neutral")


class BollingerBreakoutStrategy(BaseStrategy):
    """Bollinger Band Volatility Breakout Strategy."""

    name = "bollinger_breakout"
    description = "Triggers on price closing outside upper or lower Bollinger Bands."

    def generate_signal(self, symbol: str, timeframe: str, df: pd.DataFrame) -> Signal:
        if df.empty or "bb_upper" not in df.columns or "bb_lower" not in df.columns:
            return Signal(action="WAIT", symbol=symbol, timeframe=timeframe, confidence=0.0, reasoning="Missing Bollinger Bands")

        curr = df.iloc[-1]
        close = float(curr["close"])
        upper = float(curr["bb_upper"])
        lower = float(curr["bb_lower"])

        if close > upper:
            return Signal(
                action="BUY",
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.82,
                reasoning=f"Upper Bollinger Band breakout: close ({close:.2f}) > upper ({upper:.2f})",
                entry_price=close,
            )
        elif close < lower:
            return Signal(
                action="SELL",
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.82,
                reasoning=f"Lower Bollinger Band breakdown: close ({close:.2f}) < lower ({lower:.2f})",
                entry_price=close,
            )

        return Signal(action="WAIT", symbol=symbol, timeframe=timeframe, confidence=0.5, reasoning="Price within Bollinger Bands")


class MultiTimeframeTrendStrategy(BaseStrategy):
    """Multi-Timeframe Trend Consensus Strategy."""

    name = "mtf_trend"
    description = "Evaluates trend alignment across multiple timeframes."

    def generate_signal(self, symbol: str, timeframe: str, df: pd.DataFrame) -> Signal:
        if df.empty or "ema_50" not in df.columns or "ema_200" not in df.columns:
            return Signal(action="WAIT", symbol=symbol, timeframe=timeframe, confidence=0.0, reasoning="Missing trend EMAs")

        curr = df.iloc[-1]
        close = float(curr["close"])
        ema50 = float(curr["ema_50"])
        ema200 = float(curr["ema_200"])

        if close > ema50 > ema200:
            return Signal(
                action="BUY",
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.90,
                reasoning="Strong bullish trend alignment: Close > EMA50 > EMA200",
                entry_price=close,
            )
        elif close < ema50 < ema200:
            return Signal(
                action="SELL",
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.90,
                reasoning="Strong bearish trend alignment: Close < EMA50 < EMA200",
                entry_price=close,
            )

        return Signal(action="WAIT", symbol=symbol, timeframe=timeframe, confidence=0.5, reasoning="Mixed trend alignment")
