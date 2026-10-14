"""
QuantX — Agent Tools: market data & technical analysis.

These are read-only. They expose live price (via the exchange client) and
stored OHLCV / indicator snapshots (via the database and the indicator engine),
so an agent can ground its reasoning in real, persisted data rather than
anything it invents.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.tools.base import Tool, ToolContext, ToolResult
from app.engines.indicators.multi_timeframe import MultiTimeframeEngine
from app.models.market_data import Candle


class _SymbolArgs(BaseModel):
    symbol: str = Field(..., min_length=3, max_length=20, description="Trading pair, e.g. BTCUSDT")


class GetPriceTool(Tool):
    name = "get_price"
    description = "Get the current live market price for a trading symbol from the exchange."
    args_model = _SymbolArgs

    async def _run(self, args: _SymbolArgs, ctx: ToolContext) -> ToolResult:
        if ctx.client is None:
            return self._err("No exchange client available in context.")
        price = await ctx.client.get_price(args.symbol.upper())
        return self._ok({"symbol": args.symbol.upper(), "price": price})


class _KlinesArgs(BaseModel):
    symbol: str = Field(..., min_length=3, max_length=20)
    timeframe: str = Field(default="1h", description="Candle interval, e.g. 15m, 1h, 4h, 1d")
    limit: int = Field(default=50, ge=1, le=500, description="Number of most-recent candles")


class GetKlinesTool(Tool):
    name = "get_klines"
    description = (
        "Get the most recent stored OHLCV candles for a symbol and timeframe, "
        "in chronological order. Reads persisted market data, not live ticks."
    )
    args_model = _KlinesArgs

    async def _run(self, args: _KlinesArgs, ctx: ToolContext) -> ToolResult:
        stmt = (
            select(Candle)
            .where(Candle.symbol == args.symbol.upper(), Candle.timeframe == args.timeframe)
            .order_by(Candle.timestamp.desc())
            .limit(args.limit)
        )
        rows = list((await ctx.session.execute(stmt)).scalars().all())
        rows.reverse()  # chronological
        candles = [
            {
                "timestamp": c.timestamp.isoformat(),
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume),
            }
            for c in rows
        ]
        if not candles:
            return self._err(
                f"No stored candles for {args.symbol.upper()} {args.timeframe}. "
                "Backfill market data first."
            )
        return self._ok({"symbol": args.symbol.upper(), "timeframe": args.timeframe, "candles": candles})


class _IndicatorArgs(BaseModel):
    symbol: str = Field(..., min_length=3, max_length=20)
    timeframes: list[str] = Field(
        default_factory=lambda: ["15m", "1h", "4h"],
        description="Timeframes to compute a multi-timeframe indicator snapshot for.",
    )


class GetIndicatorsTool(Tool):
    name = "get_indicators"
    description = (
        "Compute a multi-timeframe technical-indicator snapshot (SMA, EMA, RSI, MACD, "
        "Bollinger, ATR, ADX, VWAP, Stochastic, OBV, Ichimoku) for a symbol from stored candles."
    )
    args_model = _IndicatorArgs

    async def _run(self, args: _IndicatorArgs, ctx: ToolContext) -> ToolResult:
        engine = MultiTimeframeEngine(ctx.session)
        snapshot = await engine.get_multi_timeframe_indicators(
            symbol=args.symbol.upper(),
            timeframes=args.timeframes,
        )
        if not any(snapshot.values()):
            return self._err(
                f"No indicator data for {args.symbol.upper()} on {args.timeframes}. "
                "The symbol may lack stored candles."
            )
        return self._ok({"symbol": args.symbol.upper(), "indicators": snapshot})
