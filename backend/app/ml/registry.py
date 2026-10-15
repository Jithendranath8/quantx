"""
QuantX — Model registry & MLflow bridge.

Keeps model artifacts and their metadata on disk under ``ml_model_dir`` with a
predictable naming scheme, and (optionally) mirrors runs to MLflow for
experiment tracking and a model registry.

Two independent concerns, deliberately decoupled:

* **On-disk artifacts** are the source of truth the predict tool reads. This
  works with zero external services, so inference never depends on MLflow being
  up.
* **MLflow** is best-effort observability: if it (or its package) is absent,
  :func:`log_run` logs a warning and returns, rather than failing training.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

EXPERIMENT_NAME = "quantx-direction"

# Anything outside this set is stripped from user-supplied artifact-name parts,
# so a crafted symbol/timeframe cannot traverse out of the model directory.
_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9]")


class ModelUnavailableError(RuntimeError):
    """Raised when a requested model artifact or its runtime is not available."""


def model_dir() -> Path:
    path = Path(get_settings().ml_model_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def artifact_stem(symbol: str, timeframe: str, backend: str) -> str:
    """Build a filesystem-safe artifact stem.

    ``symbol``/``timeframe`` originate from user input, so every component is
    stripped to alphanumerics. Without this a value like ``../../etc`` would let
    a model path escape ``ml_model_dir`` (path traversal).
    """
    safe_symbol = _SAFE_COMPONENT.sub("", symbol.upper())
    safe_timeframe = _SAFE_COMPONENT.sub("", timeframe)
    safe_backend = _SAFE_COMPONENT.sub("", backend)
    return f"{safe_symbol}_{safe_timeframe}_{safe_backend}"


def artifact_paths(symbol: str, timeframe: str, backend: str) -> tuple[Path, Path]:
    """Return (weights_path, metadata_path) for a model."""
    stem = artifact_stem(symbol, timeframe, backend)
    ext = "pt" if backend == "torch" else "keras"
    base = model_dir()
    return base / f"{stem}.{ext}", base / f"{stem}.json"


def save_metadata(meta_path: Path, meta: dict[str, Any]) -> None:
    meta_path.write_text(json.dumps(meta, indent=2, default=str))


def load_metadata(meta_path: Path) -> dict[str, Any] | None:
    if not meta_path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(meta_path.read_text())
        return data
    except json.JSONDecodeError:
        logger.warning("model_metadata_unreadable", path=str(meta_path))
        return None


def latest_metadata(symbol: str, timeframe: str, prefer: str = "torch") -> dict[str, Any] | None:
    """Return metadata for an available model, preferring ``prefer`` backend."""
    order = [prefer] + [b for b in ("torch", "tensorflow") if b != prefer]
    for backend in order:
        _, meta_path = artifact_paths(symbol, timeframe, backend)
        meta = load_metadata(meta_path)
        if meta is not None:
            return meta
    return None


def log_run(
    params: dict[str, Any],
    metrics: dict[str, float],
    artifacts: list[str] | None = None,
    run_name: str | None = None,
) -> str | None:
    """Best-effort MLflow logging. Returns the run id, or None if unavailable.

    MLflow being absent or misconfigured must never fail a training run, so all
    errors here degrade to a warning.
    """
    try:
        import mlflow
    except ImportError:
        logger.warning("mlflow_not_installed", hint="pip install '.[ml]' to enable tracking")
        return None

    settings = get_settings()
    try:
        if settings.mlflow_tracking_uri:
            mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        else:
            # Local file store so tracking works with no server.
            mlflow.set_tracking_uri(f"file:{os.path.abspath('mlruns')}")
        mlflow.set_experiment(EXPERIMENT_NAME)
        with mlflow.start_run(run_name=run_name) as run:
            mlflow.log_params(params)
            mlflow.log_metrics(metrics)
            for artifact in artifacts or []:
                if os.path.exists(artifact):
                    mlflow.log_artifact(artifact)
            return str(run.info.run_id)
    except Exception as exc:
        logger.warning("mlflow_logging_failed", error=str(exc))
        return None
