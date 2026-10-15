"""
QuantX — Model inference.

Loads the latest trained artifact for a symbol/timeframe and scores the current
market window into a next-bar-direction probability. The metadata sidecar is
authoritative: the exact feature list, sequence length and standardization stats
used at training time are read back here, so inference input always matches what
the model was trained on.

Any missing runtime (torch/tensorflow not installed) or missing artifact raises
:class:`ModelUnavailableError`, which the predict tool turns into a graceful,
informative result rather than an error.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from app.ml.dataset import build_feature_frame, latest_sequence
from app.ml.registry import ModelUnavailableError, artifact_paths, latest_metadata

if TYPE_CHECKING:
    import pandas as pd


def predict_direction(
    candles: pd.DataFrame | list[dict[str, Any]],
    symbol: str,
    timeframe: str,
    prefer: str = "torch",
) -> dict[str, Any]:
    """Score the most recent window and return a direction prediction."""
    meta = latest_metadata(symbol, timeframe, prefer)
    if meta is None:
        raise ModelUnavailableError(
            f"No trained model for {symbol.upper()} {timeframe}. Train one with scripts/train_model.sh."
        )

    df = build_feature_frame(candles)
    sequence_length = int(meta["sequence_length"])
    seq = latest_sequence(df, sequence_length)  # (1, L, F)

    mean = np.asarray(meta["scaler"]["mean"], dtype=np.float32)
    std = np.asarray(meta["scaler"]["std"], dtype=np.float32)
    seq = ((seq - mean) / std).astype(np.float32)

    backend = meta["backend"]
    if backend == "torch":
        prob = _torch_predict(meta, symbol, timeframe, seq)
    elif backend == "tensorflow":
        prob = _tf_predict(symbol, timeframe, seq)
    else:
        raise ModelUnavailableError(f"Unknown model backend {backend!r}")

    metrics = meta.get("metrics", {})
    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "direction": "UP" if prob >= 0.5 else "DOWN",
        "probability_up": round(prob, 4),
        # 0 at a coin-flip, 1 at full confidence either way.
        "confidence": round(abs(prob - 0.5) * 2, 4),
        "backend": backend,
        "model_version": meta.get("model_version"),
        "val_accuracy": metrics.get("val_accuracy"),
        "val_auc": metrics.get("val_auc"),
    }


def _torch_predict(meta: dict[str, Any], symbol: str, timeframe: str, seq: np.ndarray) -> float:
    try:
        import torch

        from app.ml.models.torch_model import build_model
    except ImportError as exc:  # pragma: no cover - exercised only without torch
        raise ModelUnavailableError("PyTorch is not installed; install the 'ml' extra.") from exc

    weights_path, _ = artifact_paths(symbol, timeframe, "torch")
    if not weights_path.exists():
        raise ModelUnavailableError(f"Model weights missing at {weights_path}")

    model = build_model(n_features=int(meta["n_features"]), hidden_size=int(meta.get("hidden", 32)))
    # weights_only=True restricts unpickling to tensors, closing the arbitrary-
    # code-execution path that torch.load otherwise opens on an untrusted file.
    model.load_state_dict(torch.load(weights_path, map_location="cpu", weights_only=True))
    model.eval()
    with torch.no_grad():
        return float(model(torch.from_numpy(seq)).item())


def _tf_predict(symbol: str, timeframe: str, seq: np.ndarray) -> float:
    try:
        import tensorflow as tf
    except ImportError as exc:  # pragma: no cover - exercised only without tensorflow
        raise ModelUnavailableError("TensorFlow is not installed; install the 'ml' extra.") from exc

    weights_path, _ = artifact_paths(symbol, timeframe, "tensorflow")
    if not weights_path.exists():
        raise ModelUnavailableError(f"Model artifact missing at {weights_path}")
    model = tf.keras.models.load_model(weights_path)
    return float(model.predict(seq, verbose=0).reshape(-1)[0])
