"""
QuantX — TensorFlow price-direction model (Keras MLP).

A second, independent backend for the same next-bar-direction task, built with
TensorFlow/Keras. It flattens the feature window and classifies it with a small
MLP. Providing two framework backends (PyTorch and TensorFlow) behind one
training/inference contract is the point: the registry and the predict tool do
not care which trained the artifact they load.

TensorFlow is an optional dependency (the ``ml`` extra). Importing this module
without it raises ImportError, which the callers treat as "backend unavailable".
"""

from __future__ import annotations

from typing import Any


def build_model(n_features: int, sequence_length: int, hidden_units: int = 64) -> Any:
    """Build and compile a Keras MLP over the flattened feature window."""
    import tensorflow as tf  # imported lazily; optional dependency

    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(sequence_length, n_features)),
            tf.keras.layers.Flatten(),
            tf.keras.layers.Dense(hidden_units, activation="relu"),
            tf.keras.layers.Dropout(0.1),
            tf.keras.layers.Dense(hidden_units // 2, activation="relu"),
            tf.keras.layers.Dense(1, activation="sigmoid"),
        ]
    )
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
        loss="binary_crossentropy",
        metrics=["accuracy"],
    )
    return model
