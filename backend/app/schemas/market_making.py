"""
QuantX — Market-Making Simulation Schemas.

Input parameters and output payload for the Avellaneda-Stoikov market-making
simulation: the quoting parameters, the per-step time series the UI charts, the
realized fills, and the headline performance metrics (with the all-important
spread-capture vs inventory P&L decomposition).
"""

from datetime import datetime

from pydantic import BaseModel, Field


class MarketMakingRequest(BaseModel):
    """Parameters for a market-making simulation."""

    symbol: str = Field(default="BTCUSDT")
    timeframe: str = Field(default="1m")
    # Quoting model.
    gamma: float = Field(default=0.3, gt=0, le=10, description="Inventory risk aversion")
    k: float = Field(default=1.5, gt=0, description="Order-book liquidity / arrival decay")
    horizon: float = Field(default=1.0, gt=0, le=1.0, description="Normalized risk horizon (T-t)")
    # Execution / inventory.
    order_size: float = Field(default=0.01, gt=0, description="Base units quoted per side")
    max_inventory: float = Field(default=1.0, gt=0, description="Inventory cap (base units, each side)")
    fee_rate: float = Field(default=0.0, ge=0, description="Per-fill fee rate (0 = maker rebate world)")
    vol_window: int = Field(default=30, ge=5, le=500, description="Bars used to estimate volatility")
    start_date: datetime | None = None
    end_date: datetime | None = None


class QuotePoint(BaseModel):
    """One step of the simulation: the mid, the quotes, inventory and equity."""

    timestamp: str
    mid: float
    bid: float
    ask: float
    inventory: float
    pnl: float


class MarketMakingFill(BaseModel):
    """A simulated fill and the spread edge it captured versus the mid."""

    timestamp: str
    side: str  # BUY or SELL
    price: float
    size: float
    edge: float


class MarketMakingMetrics(BaseModel):
    """Headline performance of the market-making run."""

    total_pnl: float
    spread_pnl: float
    inventory_pnl: float
    fees_paid: float
    num_fills: int
    num_buys: int
    num_sells: int
    fill_ratio: float
    sharpe_ratio: float
    max_inventory: float
    final_inventory: float
    avg_spread_bps: float


class MarketMakingResult(BaseModel):
    """Full market-making simulation output payload."""

    symbol: str
    timeframe: str
    params: MarketMakingRequest
    metrics: MarketMakingMetrics
    series: list[QuotePoint]
    fills: list[MarketMakingFill]
