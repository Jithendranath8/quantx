"""
QuantX — Analytics & Portfolio Pydantic Schemas.
"""

from pydantic import BaseModel, Field


class AssetAllocation(BaseModel):
    """Asset allocation breakdown item."""

    symbol: str
    allocation_pct: float
    value_usd: float


class PortfolioSummary(BaseModel):
    """Overall portfolio performance summary."""

    total_equity_usd: float
    cash_balance_usd: float
    realized_pnl_usd: float
    unrealized_pnl_usd: float
    win_rate_pct: float | None = Field(
        default=None,
        description="Win rate over closed positions; null when no position has closed yet",
    )
    total_trades_count: int
    closed_trades_count: int = 0
    open_positions_count: int
    allocations: list[AssetAllocation]


class TradeExportItem(BaseModel):
    """Trade record export row."""

    trade_id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    exit_price: float | None = None
    realized_pnl: float
    status: str
    timestamp: str
