"""
QuantX — Agent Tools: strategies & backtesting.

Lets an agent discover the registered strategies and run a real event-driven
backtest over stored candles — so a claim like "this setup historically works"
can be checked against measured performance instead of asserted.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.tools.base import Tool, ToolContext, ToolResult
from app.schemas.backtest import BacktestRequest
from app.services.backtest_service import BacktestService
from app.services.strategy_service import StrategyService


class _NoArgs(BaseModel):
    pass


class ListStrategiesTool(Tool[_NoArgs]):
    name = "list_strategies"
    description = "List the available trading strategies and their tunable parameters."
    args_model = _NoArgs

    async def _run(self, args: _NoArgs, ctx: ToolContext) -> ToolResult:
        strategies = StrategyService(ctx.session).list_available_strategies()
        return self._ok({"strategies": strategies})


class _BacktestArgs(BaseModel):
    symbol: str = Field(default="BTCUSDT", min_length=3, max_length=20)
    timeframe: str = Field(default="1h")
    strategy_name: str = Field(default="ema_crossover")
    initial_capital: float = Field(default=10_000.0, ge=100.0)


class RunBacktestTool(Tool[_BacktestArgs]):
    name = "run_backtest"
    description = (
        "Run an event-driven backtest of a strategy over stored candles and return "
        "performance metrics (return %, Sharpe, max drawdown, win rate, profit factor, trade count)."
    )
    args_model = _BacktestArgs

    async def _run(self, args: _BacktestArgs, ctx: ToolContext) -> ToolResult:
        req = BacktestRequest(
            symbol=args.symbol.upper(),
            timeframe=args.timeframe,
            strategy_name=args.strategy_name,
            initial_capital=args.initial_capital,
        )
        result = await BacktestService(ctx.session).run_backtest(req)
        # Return the summary only; the full equity curve would blow the token budget.
        return self._ok(
            {
                "symbol": result.symbol,
                "timeframe": result.timeframe,
                "strategy_name": result.strategy_name,
                "final_equity": result.final_equity,
                "metrics": result.metrics.model_dump(),
            }
        )
