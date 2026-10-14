#!/usr/bin/env bash
# =====================================================================
# QuantX — train a price-direction model.
#
# Trains the PyTorch (default) or TensorFlow backend on stored candles and
# writes the artifact + metadata under $ML_MODEL_DIR (default ./ml_artifacts),
# logging the run to MLflow (local ./mlruns unless MLFLOW_TRACKING_URI is set).
#
# Usage:
#   scripts/train_model.sh [SYMBOL] [TIMEFRAME] [BACKEND] [EPOCHS]
# Examples:
#   scripts/train_model.sh                      # BTCUSDT 1h torch 20
#   scripts/train_model.sh ETHUSDT 4h torch 30
#   scripts/train_model.sh BTCUSDT 1h tensorflow 25
#
# Run inside the backend container (needs DB access and the 'ml' extra):
#   docker compose exec backend scripts/train_model.sh BTCUSDT 1h
# =====================================================================
set -euo pipefail

SYMBOL="${1:-BTCUSDT}"
TIMEFRAME="${2:-1h}"
BACKEND="${3:-torch}"
EPOCHS="${4:-20}"

echo "[train] symbol=$SYMBOL timeframe=$TIMEFRAME backend=$BACKEND epochs=$EPOCHS"
python -m app.ml.cli train \
  --symbol "$SYMBOL" \
  --timeframe "$TIMEFRAME" \
  --backend "$BACKEND" \
  --epochs "$EPOCHS"
echo "[train] done — artifact written under ${ML_MODEL_DIR:-./ml_artifacts}"
