"""
QuantX — PyTorch price-direction model (LSTM classifier).

A small recurrent classifier that reads a window of engineered features and
predicts the probability that the next bar closes higher. Kept deliberately
compact so it trains in seconds on CPU over a few hundred candles, which is all
a demo or a unit test needs, while remaining a genuine sequence model.

This module imports ``torch`` at import time by design: nothing in the app
start-up path imports it — only the training and inference code does, and only
when ML is actually requested — so the lean backend image never pays for it.
"""

from __future__ import annotations

import torch
from torch import nn


class DirectionLSTM(nn.Module):  # type: ignore[misc]  # torch is an optional, unstubbed dependency
    """LSTM → dropout → linear → sigmoid, emitting P(next bar up)."""

    def __init__(self, n_features: int, hidden_size: int = 32, num_layers: int = 1, dropout: float = 0.1) -> None:
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=n_features,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.dropout = nn.Dropout(dropout)
        self.head = nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, seq_len, n_features)
        output, _ = self.lstm(x)
        last = output[:, -1, :]  # final timestep representation
        logits = self.head(self.dropout(last)).squeeze(-1)
        return torch.sigmoid(logits)


def build_model(n_features: int, hidden_size: int = 32, num_layers: int = 1) -> DirectionLSTM:
    return DirectionLSTM(n_features=n_features, hidden_size=hidden_size, num_layers=num_layers)
