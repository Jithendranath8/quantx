"""
QuantX — Machine-learning subsystem.

Feature engineering and the model registry are pure (pandas/numpy) and safe to
import anywhere. The model backends (``app.ml.models.*``), ``training`` and
``inference`` import torch/tensorflow and are therefore imported lazily, only
when ML is actually used, so the lean backend image never loads a deep-learning
runtime it will not use.
"""

from __future__ import annotations

from app.ml.dataset import FEATURE_COLUMNS, build_feature_frame, build_sequences, latest_sequence
from app.ml.registry import ModelUnavailable, latest_metadata

__all__ = [
    "FEATURE_COLUMNS",
    "build_feature_frame",
    "build_sequences",
    "latest_sequence",
    "ModelUnavailable",
    "latest_metadata",
]
