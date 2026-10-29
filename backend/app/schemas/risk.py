"""
QuantX — Risk Engine Pydantic Schemas.

Configurable hard risk rules and validation result payloads.
"""

from pydantic import BaseModel, Field


class RiskConfig(BaseModel):
    """Configurable risk parameters enforced by the Risk Engine."""

    max_risk_per_trade_pct: float = Field(default=0.02, description="Max risk per trade as % of account balance (0.02 = 2%)")
    max_daily_loss_pct: float = Field(default=0.05, description="Max allowed daily loss % before circuit breaker triggers (0.05 = 5%)")
    max_leverage: int = Field(default=10, description="Max allowed leverage")
    max_portfolio_exposure_pct: float = Field(default=0.50, description="Max combined portfolio exposure (0.50 = 50%)")
    max_concurrent_trades: int = Field(default=5, description="Max concurrent open positions")
    cooldown_period_minutes: int = Field(default=15, description="Minutes a symbol cannot be bought again after a losing exit in it")
    circuit_breaker_active: bool = Field(default=False, description="Manual or automatic circuit breaker state")


class TradeRiskRequest(BaseModel):
    """Trade proposal payload sent to Risk Engine for validation."""

    symbol: str
    action: str  # BUY / SELL
    account_balance: float
    order_amount_usd: float
    leverage: int = 1
    stop_loss_price: float | None = None
    entry_price: float
    current_daily_loss_usd: float = 0.0
    active_positions_count: int = 0
    current_exposure_usd: float = 0.0
    # Minutes since the account last closed a losing trade in this symbol, or
    # None when there is no such exit (or the caller cannot know).
    minutes_since_loss_on_symbol: float | None = None


class RiskCheckResult(BaseModel):
    """Output payload from Risk Engine validation."""

    is_approved: bool
    rejection_reason: str | None = None
    max_allowed_position_size_usd: float
    recommended_position_size_usd: float
    circuit_breaker_triggered: bool = False
