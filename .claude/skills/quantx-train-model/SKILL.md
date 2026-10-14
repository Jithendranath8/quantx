---
name: quantx-train-model
description: Train, evaluate or inspect the QuantX price-direction ML model (PyTorch LSTM or TensorFlow MLP) on stored candles, with MLflow tracking. Use when asked to train/retrain a model, check model metrics, or get an ML prediction for a symbol.
---

# QuantX ML model training

Train and operate the next-bar-direction model that backs the agent's
`predict_direction` tool.

## Prerequisites
- The ML extra must be installed: `pip install -e '.[ml]'`.
- On Linux/Mac CPU install the CPU-only torch wheel first, so pip does not pull
  the multi-GB CUDA build:
  `pip install torch --index-url https://download.pytorch.org/whl/cpu`
- Candles for the symbol/timeframe must be backfilled.

## Commands
Run inside the backend container (it has DB access):

```bash
# train (PyTorch is default; use tensorflow for the second backend)
docker compose exec backend scripts/train_model.sh BTCUSDT 1h torch 20
docker compose exec backend scripts/train_model.sh BTCUSDT 1h tensorflow 25

# evaluate stored metrics + run a live prediction on latest candles
docker compose exec backend scripts/eval_model.sh BTCUSDT 1h torch
```

Or the CLI directly: `python -m app.ml.cli train|evaluate|predict --symbol ... --timeframe ...`.

## What to report
- Train/validation accuracy and AUC (from the metadata sidecar / MLflow run).
- Be honest about near-0.5 metrics: next-bar direction is a hard target and a
  weak model is expected to be near chance. Do not oversell it.
- The artifact location (`$ML_MODEL_DIR`, default `./ml_artifacts`) and the
  MLflow run id (local `./mlruns` unless `MLFLOW_TRACKING_URI` is set).

## Notes
- Metadata records the exact feature list, sequence length and scaler, so
  inference input always matches training. Never hand-edit it.
- Training writes to disk; keep an eye on space (the CUDA torch wheel is the
  usual cause of disk blowups — always use the CPU wheel on this machine).
