"""
QuantX — Model training pipeline.

Trains a next-bar-direction classifier (PyTorch LSTM or TensorFlow MLP) on a
feature frame, evaluates it on a time-ordered holdout, writes the weights plus a
self-describing metadata sidecar (feature list, sequence length, standardization
stats, metrics, provenance), and logs the run to MLflow.

The metadata is what makes inference reproducible: it records exactly which
features in which order and which scaler the model expects, so the predict path
can never silently feed the model the wrong input.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from app.core.logging import get_logger
from app.ml.dataset import FEATURE_COLUMNS, build_sequences
from app.ml.registry import artifact_paths, log_run, save_metadata

logger = get_logger(__name__)

MIN_SAMPLES = 40


def train_torch(
    df: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    sequence_length: int = 16,
    epochs: int = 20,
    hidden_size: int = 32,
    lr: float = 1e-3,
    seed: int = 42,
) -> dict[str, Any]:
    """Train the PyTorch LSTM and persist artifacts. Returns the metadata dict."""
    import torch
    from torch import nn

    from app.ml.models.torch_model import build_model

    torch.manual_seed(seed)
    np.random.seed(seed)

    x, y, scaler = _prepare(df, sequence_length)
    (x_tr, y_tr), (x_val, y_val) = _time_split(x, y)

    model = build_model(n_features=x.shape[2], hidden_size=hidden_size)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.BCELoss()

    x_tr_t = torch.from_numpy(x_tr)
    y_tr_t = torch.from_numpy(y_tr)

    model.train()
    for epoch in range(epochs):
        optimizer.zero_grad()
        preds = model(x_tr_t)
        loss = loss_fn(preds, y_tr_t)
        loss.backward()
        optimizer.step()
        if epoch % 5 == 0:
            logger.info("torch_train_epoch", epoch=epoch, loss=float(loss.item()))

    model.eval()
    with torch.no_grad():
        val_scores = model(torch.from_numpy(x_val)).numpy() if len(x_val) else np.array([])
        train_scores = model(x_tr_t).numpy()

    metrics = _metrics(y_tr, train_scores, y_val, val_scores)
    weights_path, meta_path = artifact_paths(symbol, timeframe, "torch")
    torch.save(model.state_dict(), weights_path)

    meta = _metadata("torch", symbol, timeframe, sequence_length, hidden_size, x, scaler, metrics)
    save_metadata(meta_path, meta)
    meta["mlflow_run_id"] = log_run(
        params={"backend": "torch", "symbol": symbol, "timeframe": timeframe,
                "sequence_length": sequence_length, "hidden_size": hidden_size, "epochs": epochs},
        metrics=metrics,
        artifacts=[str(weights_path), str(meta_path)],
        run_name=f"torch-{symbol}-{timeframe}",
    )
    logger.info("torch_model_trained", symbol=symbol, timeframe=timeframe, **metrics)
    return meta


def train_tensorflow(
    df: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    sequence_length: int = 16,
    epochs: int = 20,
    hidden_units: int = 64,
    seed: int = 42,
) -> dict[str, Any]:
    """Train the TensorFlow MLP and persist artifacts. Returns the metadata dict."""
    import tensorflow as tf

    from app.ml.models.tf_model import build_model

    tf.random.set_seed(seed)
    np.random.seed(seed)

    x, y, scaler = _prepare(df, sequence_length)
    (x_tr, y_tr), (x_val, y_val) = _time_split(x, y)

    model = build_model(n_features=x.shape[2], sequence_length=sequence_length, hidden_units=hidden_units)
    validation = (x_val, y_val) if len(x_val) else None
    model.fit(x_tr, y_tr, epochs=epochs, batch_size=32, verbose=0, validation_data=validation)

    train_scores = model.predict(x_tr, verbose=0).reshape(-1)
    val_scores = model.predict(x_val, verbose=0).reshape(-1) if len(x_val) else np.array([])
    metrics = _metrics(y_tr, train_scores, y_val, val_scores)

    weights_path, meta_path = artifact_paths(symbol, timeframe, "tensorflow")
    model.save(weights_path)
    meta = _metadata("tensorflow", symbol, timeframe, sequence_length, hidden_units, x, scaler, metrics)
    save_metadata(meta_path, meta)
    meta["mlflow_run_id"] = log_run(
        params={"backend": "tensorflow", "symbol": symbol, "timeframe": timeframe,
                "sequence_length": sequence_length, "hidden_units": hidden_units, "epochs": epochs},
        metrics=metrics,
        artifacts=[str(meta_path)],
        run_name=f"tf-{symbol}-{timeframe}",
    )
    logger.info("tf_model_trained", symbol=symbol, timeframe=timeframe, **metrics)
    return meta


# ── shared helpers ───────────────────────────────────────────────────


def _prepare(df: pd.DataFrame, sequence_length: int) -> tuple[np.ndarray, np.ndarray, dict[str, list[float]]]:
    x, y = build_sequences(df, sequence_length)
    if len(x) < MIN_SAMPLES:
        raise ValueError(f"not enough samples to train: {len(x)} < {MIN_SAMPLES}")
    # Standardize per feature using stats over all training windows.
    mean = x.reshape(-1, x.shape[2]).mean(axis=0)
    std = x.reshape(-1, x.shape[2]).std(axis=0) + 1e-9
    x = ((x - mean) / std).astype(np.float32)
    scaler = {"mean": mean.tolist(), "std": std.tolist()}
    return x, y, scaler


def _time_split(x: np.ndarray, y: np.ndarray, val_frac: float = 0.2):
    """Time-ordered split: earliest for train, most recent for validation."""
    n_val = max(1, int(len(x) * val_frac))
    split = len(x) - n_val
    return (x[:split], y[:split]), (x[split:], y[split:])


def _metrics(y_tr: np.ndarray, s_tr: np.ndarray, y_val: np.ndarray, s_val: np.ndarray) -> dict[str, float]:
    out = {
        "train_accuracy": _accuracy(y_tr, s_tr),
        "train_auc": _auc(y_tr, s_tr),
    }
    if len(y_val):
        out["val_accuracy"] = _accuracy(y_val, s_val)
        out["val_auc"] = _auc(y_val, s_val)
    return out


def _accuracy(y_true: np.ndarray, scores: np.ndarray) -> float:
    if len(y_true) == 0:
        return 0.0
    preds = (scores >= 0.5).astype(np.float32)
    return float((preds == y_true).mean())


def _auc(y_true: np.ndarray, scores: np.ndarray) -> float:
    """Rank-based ROC-AUC (Mann-Whitney U); 0.5 when one class is absent."""
    pos = scores[y_true == 1]
    neg = scores[y_true == 0]
    if len(pos) == 0 or len(neg) == 0:
        return 0.5
    order = scores.argsort()
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, len(scores) + 1)
    rank_sum_pos = ranks[y_true == 1].sum()
    auc = (rank_sum_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))
    return float(auc)


def _metadata(
    backend: str,
    symbol: str,
    timeframe: str,
    sequence_length: int,
    hidden: int,
    x: np.ndarray,
    scaler: dict[str, list[float]],
    metrics: dict[str, float],
) -> dict[str, Any]:
    return {
        "backend": backend,
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "feature_columns": FEATURE_COLUMNS,
        "sequence_length": sequence_length,
        "n_features": int(x.shape[2]),
        "hidden": hidden,
        "scaler": scaler,
        "metrics": metrics,
        "n_samples": int(len(x)),
        "trained_at": datetime.now(UTC).isoformat(),
        "model_version": datetime.now(UTC).strftime("%Y%m%d%H%M%S"),
        "git_commit": _git_commit(),
    }


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:  # noqa: BLE001 — provenance is best-effort
        return None
