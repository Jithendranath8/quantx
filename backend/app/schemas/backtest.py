"""
QuantX — Backtest Engine Schemas.

Defines input parameters and output performance metrics for backtests.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.validators import Symbol, Timeframe


class BacktestRequest(BaseModel):
    """Parameters for running a backtest simulation."""

    symbol: Symbol = Field(default="BTCUSDT")
    timeframe: Timeframe = Field(default="1h")
    strategy_name: str = Field(default="ema_crossover", pattern=r"^[a-z0-9_]{1,64}$")
    initial_capital: float = Field(default=10000.0, ge=100.0, le=1e12, allow_inf_nan=False)
    # Costs are fractions of notional. Bounded so a negative or absurd value
    # cannot turn the simulator into a money printer or overflow its arithmetic.
    fee_rate: float = Field(default=0.00075, ge=0.0, le=0.1, description="Maker/Taker fee (0.00075 = 0.075%)")
    slippage: float = Field(default=0.0005, ge=0.0, le=0.1, description="Slippage model (0.0005 = 0.05%)")
    start_date: datetime | None = None
    end_date: datetime | None = None


class EquityPoint(BaseModel):
    """Timestamped point on the equity curve."""

    timestamp: str
    equity: float
    drawdown_pct: float


class BacktestMetrics(BaseModel):
    """Institutional backtesting performance metrics."""

    total_return_pct: float
    net_profit_usd: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_trade_pnl_usd: float


class BacktestResult(BaseModel):
    """Full backtest simulation output payload."""

    symbol: str
    timeframe: str
    strategy_name: str
    initial_capital: float
    final_equity: float
    metrics: BacktestMetrics
    equity_curve: list[EquityPoint]
    trades: list[dict[str, Any]]
