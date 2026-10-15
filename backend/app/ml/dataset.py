"""
QuantX — ML dataset & feature engineering.

Pure pandas/numpy (no torch/tensorflow), so it is always importable and
testable even in the lean backend image. Turns stored OHLCV candles into a
supervised next-bar-direction dataset:

  * features: returns over several horizons, realized volatility, high-low
    range, a volume z-score, an SMA ratio and RSI(14) — all derived only from
    the candle series itself, so there is no look-ahead.
  * label: 1 if the next bar closes higher than this one, else 0.

The sequence builder emits ``(N, sequence_length, n_features)`` windows for the
recurrent model; the final incomplete window (whose label would require an
unseen future bar) is dropped.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

FEATURE_COLUMNS: list[str] = [
    "ret_1",
    "ret_5",
    "ret_10",
    "volatility_10",
    "hl_range",
    "volume_z",
    "sma_ratio",
    "rsi_14",
]


def build_feature_frame(candles: pd.DataFrame | list[dict[str, Any]]) -> pd.DataFrame:
    """Compute the feature columns and the next-bar direction label.

    Rows with NaNs from warm-up windows (and the final row, whose forward label
    is unknown) are dropped, so every returned row is fully usable.
    """
    df = pd.DataFrame(candles) if not isinstance(candles, pd.DataFrame) else candles.copy()
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"candles missing columns: {sorted(missing)}")

    df = df.reset_index(drop=True)
    close = df["close"].astype(float)

    df["ret_1"] = close.pct_change()
    df["ret_5"] = close.pct_change(5)
    df["ret_10"] = close.pct_change(10)
    df["volatility_10"] = df["ret_1"].rolling(10).std()
    df["hl_range"] = (df["high"].astype(float) - df["low"].astype(float)) / close
    vol = df["volume"].astype(float)
    df["volume_z"] = (vol - vol.rolling(20).mean()) / (vol.rolling(20).std() + 1e-9)
    df["sma_ratio"] = close / (close.rolling(20).mean()) - 1.0
    df["rsi_14"] = _rsi(close, 14)

    # Next-bar direction label.
    df["label"] = (close.shift(-1) > close).astype(int)
    # The last row's label used shift(-1) of itself (NaN-compared -> 0); drop it.
    df = df.iloc[:-1]

    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=[*FEATURE_COLUMNS, "label"])
    return df.reset_index(drop=True)


def build_sequences(
    df: pd.DataFrame, sequence_length: int = 16
) -> tuple[np.ndarray, np.ndarray]:
    """Return (X, y): X is (N, sequence_length, n_features), y is (N,)."""
    if sequence_length < 1:
        raise ValueError("sequence_length must be >= 1")
    features = df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    labels = df["label"].to_numpy(dtype=np.float32)
    n = len(df) - sequence_length + 1
    if n <= 0:
        return (
            np.empty((0, sequence_length, len(FEATURE_COLUMNS)), dtype=np.float32),
            np.empty((0,), dtype=np.float32),
        )
    xs = np.stack([features[i : i + sequence_length] for i in range(n)])
    # Label aligns with the last bar of each window.
    ys = labels[sequence_length - 1 :]
    return xs, ys


def latest_sequence(df: pd.DataFrame, sequence_length: int = 16) -> np.ndarray:
    """The most recent single window, shaped (1, sequence_length, n_features).

    Used at inference time to score the current market state.
    """
    features = df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    if len(features) < sequence_length:
        raise ValueError(f"need >= {sequence_length} feature rows, have {len(features)}")
    window = features[-sequence_length:]
    reshaped: np.ndarray = window.reshape(1, sequence_length, len(FEATURE_COLUMNS))
    return reshaped


def _rsi(close: pd.Series, period: int) -> pd.Series:
    """Wilder-smoothed RSI, matching the platform's indicator convention."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    return 100.0 - (100.0 / (1.0 + rs))
