"""
QuantX — ML command-line entrypoint.

A thin CLI the bash scripts (and a human) drive to train, evaluate and query
models against the real candle store:

    python -m app.ml.cli train    --symbol BTCUSDT --timeframe 1h --backend torch
    python -m app.ml.cli evaluate  --symbol BTCUSDT --timeframe 1h
    python -m app.ml.cli predict   --symbol BTCUSDT --timeframe 1h

Candles are loaded from PostgreSQL via the app's own async session, so training
uses exactly the data the platform serves — no separate export step.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

import pandas as pd
from sqlalchemy import select

from app.core.database import get_session_factory
from app.models.market_data import Candle


async def _load_candles(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    async with get_session_factory()() as session:
        stmt = (
            select(Candle)
            .where(Candle.symbol == symbol.upper(), Candle.timeframe == timeframe)
            .order_by(Candle.timestamp.desc())
            .limit(limit)
        )
        rows = list((await session.execute(stmt)).scalars().all())
    rows.reverse()
    return pd.DataFrame(
        [
            {
                "timestamp": c.timestamp,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume),
            }
            for c in rows
        ]
    )


def _train(args: argparse.Namespace) -> dict[str, Any]:
    from app.ml.dataset import build_feature_frame
    from app.ml.training import train_tensorflow, train_torch

    raw = asyncio.run(_load_candles(args.symbol, args.timeframe, args.candles))
    if raw.empty:
        raise SystemExit(f"No candles for {args.symbol} {args.timeframe}. Backfill market data first.")
    df = build_feature_frame(raw)

    if args.backend == "tensorflow":
        return train_tensorflow(
            df, symbol=args.symbol, timeframe=args.timeframe,
            sequence_length=args.sequence_length, epochs=args.epochs,
        )
    return train_torch(
        df, symbol=args.symbol, timeframe=args.timeframe,
        sequence_length=args.sequence_length, epochs=args.epochs,
    )


def _evaluate(args: argparse.Namespace) -> dict[str, Any]:
    from app.ml.registry import latest_metadata

    meta = latest_metadata(args.symbol, args.timeframe, prefer=args.backend)
    if meta is None:
        raise SystemExit(f"No trained model for {args.symbol} {args.timeframe}.")
    return {"symbol": meta["symbol"], "timeframe": meta["timeframe"], "backend": meta["backend"],
            "model_version": meta.get("model_version"), "metrics": meta.get("metrics", {})}


def _predict(args: argparse.Namespace) -> dict[str, Any]:
    from app.ml.inference import predict_direction

    raw = asyncio.run(_load_candles(args.symbol, args.timeframe, args.candles))
    if raw.empty:
        raise SystemExit(f"No candles for {args.symbol} {args.timeframe}.")
    return predict_direction(raw, args.symbol, args.timeframe, prefer=args.backend)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="app.ml.cli", description="QuantX ML pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("train", "evaluate", "predict"):
        p = sub.add_parser(name)
        p.add_argument("--symbol", default="BTCUSDT")
        p.add_argument("--timeframe", default="1h")
        p.add_argument("--backend", default="torch", choices=["torch", "tensorflow"])
        p.add_argument("--candles", type=int, default=2000)
        p.add_argument("--sequence-length", type=int, default=16)
        p.add_argument("--epochs", type=int, default=20)

    args = parser.parse_args(argv)
    handler = {"train": _train, "evaluate": _evaluate, "predict": _predict}[args.command]
    result = handler(args)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
