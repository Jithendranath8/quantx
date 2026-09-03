"""
QuantX — Backtest Engine Schemas.

Defines input parameters and output performance metrics for backtests.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    """Parameters for running a backtest simulation."""

    symbol: str = Field(default="BTCUSDT")
    timeframe: str = Field(default="1h")
    strategy_name: str = Field(default="ema_crossover")
    initial_capital: float = Field(default=10000.0, ge=100.0)
    fee_rate: float = Field(default=0.00075, description="Maker/Taker fee (0.00075 = 0.075%)")
    slippage: float = Field(default=0.0005, description="Slippage model (0.0005 = 0.05%)")
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
    trades: list[dict]
