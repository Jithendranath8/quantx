#!/usr/bin/env bash
# =====================================================================
# QuantX — evaluate / inspect a trained model.
#
# Prints the stored validation metrics for a model, then runs a live prediction
# on the most recent candles so you can see what it currently signals.
#
# Usage:
#   scripts/eval_model.sh [SYMBOL] [TIMEFRAME] [BACKEND]
# Example:
#   docker compose exec backend scripts/eval_model.sh BTCUSDT 1h torch
# =====================================================================
set -euo pipefail

SYMBOL="${1:-BTCUSDT}"
TIMEFRAME="${2:-1h}"
BACKEND="${3:-torch}"

echo "[eval] stored metrics for $SYMBOL $TIMEFRAME ($BACKEND):"
python -m app.ml.cli evaluate --symbol "$SYMBOL" --timeframe "$TIMEFRAME" --backend "$BACKEND"

echo "[eval] live prediction on latest candles:"
python -m app.ml.cli predict --symbol "$SYMBOL" --timeframe "$TIMEFRAME" --backend "$BACKEND"
