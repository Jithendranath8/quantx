"""
QuantX — Agent Tool: ML price-direction prediction.

Exposes the trained model to the agent as a read-only prediction tool. It loads
the latest artifact for the symbol/timeframe and scores the current window.

If no model has been trained, or the deep-learning runtime is not installed,
the tool returns a structured, non-fatal message (``ok=False`` with guidance)
rather than raising — so an agent simply proceeds without an ML signal instead
of the run collapsing.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.tools.base import Tool, ToolContext, ToolResult
from app.models.market_data import Candle

# Enough history to form a feature window plus indicator warm-up.
_PREDICT_CANDLES = 120


class _PredictArgs(BaseModel):
    symbol: str = Field(..., min_length=3, max_length=20)
    timeframe: str = Field(default="1h")


class PredictDirectionTool(Tool[_PredictArgs]):
    name = "predict_direction"
    description = (
        "Predict the probability that the next bar closes higher, using the trained ML model "
        "(PyTorch/TensorFlow) for this symbol and timeframe. Returns direction, probability and "
        "the model's validation metrics. If no model is trained, says so without failing."
    )
    args_model = _PredictArgs

    async def _run(self, args: _PredictArgs, ctx: ToolContext) -> ToolResult:
        from app.ml.registry import ModelUnavailableError

        stmt = (
            select(Candle)
            .where(Candle.symbol == args.symbol.upper(), Candle.timeframe == args.timeframe)
            .order_by(Candle.timestamp.desc())
            .limit(_PREDICT_CANDLES)
        )
        rows = list((await ctx.session.execute(stmt)).scalars().all())
        rows.reverse()
        if len(rows) < 30:
            return self._err(
                f"Not enough stored candles for {args.symbol.upper()} {args.timeframe} to form a "
                "feature window (need ~30+). Backfill market data first."
            )

        candles = [
            {
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume),
            }
            for c in rows
        ]

        # Imported lazily so the tool is usable (and degrades cleanly) even where
        # torch/tensorflow are not installed.
        try:
            from app.ml.inference import predict_direction
        except ImportError:
            return self._err("ML runtime not installed. Install the 'ml' extra to enable predictions.")

        try:
            prediction = predict_direction(candles, args.symbol.upper(), args.timeframe)
        except ModelUnavailableError as exc:
            return self._err(str(exc))

        return self._ok(prediction)
