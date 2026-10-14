"""
QuantX — ML subsystem tests.

Three layers:
  * feature engineering / dataset (pure numpy/pandas, no deep-learning runtime);
  * a real PyTorch train → persist → predict roundtrip (skipped if torch is
    not installed), proving the pipeline produces a loadable, scoring model;
  * the predict agent tool's graceful degradation when no model is trained.
"""

from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools import build_default_registry
from app.agents.tools.base import ToolContext
from app.core.config import get_settings
from app.ml.dataset import FEATURE_COLUMNS, build_feature_frame, build_sequences, latest_sequence


def _synthetic_candles(n: int = 600, seed: int = 7) -> pd.DataFrame:
    """A trending series with noise, so both up and down labels occur."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0005, 0.01, size=n).cumsum()
    close = 50_000 * np.exp(steps)
    high = close * (1 + rng.uniform(0.0, 0.005, size=n))
    low = close * (1 - rng.uniform(0.0, 0.005, size=n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    volume = rng.uniform(80, 120, size=n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})


# ── features / dataset (pure) ─────────────────────────────────────────


def test_feature_frame_has_all_columns_and_no_nans() -> None:
    df = build_feature_frame(_synthetic_candles())
    for col in [*FEATURE_COLUMNS, "label"]:
        assert col in df.columns
    assert not df[FEATURE_COLUMNS].isna().any().any()
    assert set(df["label"].unique()) <= {0, 1}


def test_label_reflects_next_bar_direction() -> None:
    rising = pd.DataFrame(
        {
            "open": np.arange(100, 200, dtype=float),
            "high": np.arange(100, 200, dtype=float) + 1,
            "low": np.arange(100, 200, dtype=float) - 1,
            "close": np.arange(100, 200, dtype=float),
            "volume": np.full(100, 100.0),
        }
    )
    df = build_feature_frame(rising)
    # strictly rising closes → every next bar is up
    assert (df["label"] == 1).all()


def test_build_sequences_shapes() -> None:
    df = build_feature_frame(_synthetic_candles())
    x, y = build_sequences(df, sequence_length=16)
    assert x.ndim == 3
    assert x.shape[1] == 16
    assert x.shape[2] == len(FEATURE_COLUMNS)
    assert x.shape[0] == y.shape[0]


def test_latest_sequence_shape() -> None:
    df = build_feature_frame(_synthetic_candles())
    seq = latest_sequence(df, sequence_length=16)
    assert seq.shape == (1, 16, len(FEATURE_COLUMNS))


def test_feature_frame_rejects_missing_columns() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        build_feature_frame(pd.DataFrame({"close": [1, 2, 3]}))


# ── real PyTorch roundtrip ────────────────────────────────────────────


def test_torch_train_predict_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("torch")
    from app.ml.inference import predict_direction
    from app.ml.registry import artifact_paths
    from app.ml.training import train_torch

    settings = get_settings()
    monkeypatch.setattr(settings, "ml_model_dir", str(tmp_path))
    monkeypatch.setattr(settings, "mlflow_tracking_uri", f"file:{tmp_path}/mlruns")

    raw = _synthetic_candles()
    df = build_feature_frame(raw)
    meta = train_torch(df, symbol="BTCUSDT", timeframe="1h", sequence_length=16, epochs=3)

    assert meta["backend"] == "torch"
    assert meta["n_features"] == len(FEATURE_COLUMNS)
    assert "train_accuracy" in meta["metrics"]
    weights_path, meta_path = artifact_paths("BTCUSDT", "1h", "torch")
    assert weights_path.exists() and meta_path.exists()

    prediction = predict_direction(raw, "BTCUSDT", "1h")
    assert prediction["direction"] in {"UP", "DOWN"}
    assert 0.0 <= prediction["probability_up"] <= 1.0
    assert 0.0 <= prediction["confidence"] <= 1.0
    assert prediction["backend"] == "torch"


# ── predict tool degradation ──────────────────────────────────────────


async def test_predict_tool_reports_missing_model(
    db_session: AsyncSession, seeded_candles: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Point the model dir at an empty location so no artifact is found.
    monkeypatch.setattr(get_settings(), "ml_model_dir", str(tmp_path))
    ctx = ToolContext(session=db_session)
    result = await build_default_registry().invoke(
        "predict_direction", {"symbol": "BTCUSDT", "timeframe": "1h"}, ctx
    )
    assert result.ok is False
    # Either torch is absent or there is simply no trained model; both are
    # reported as a clean message, never an exception.
    assert isinstance(result.error, str) and result.error
    _ = cast("str", result.error)


# ── security: artifact path sanitization ──────────────────────────────


def test_artifact_stem_strips_path_traversal() -> None:
    """User-supplied symbol/timeframe must never escape the model directory."""
    from app.ml.registry import artifact_stem

    stem = artifact_stem("../../etc/passwd", "1h/../x", "torch")
    assert "/" not in stem
    assert ".." not in stem
    assert stem == "ETCPASSWD_1hx_torch"
