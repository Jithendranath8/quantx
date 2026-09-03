"""
QuantX — Paper Trading Pydantic Schemas.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CreatePaperAccountRequest(BaseModel):
    """Request to create a new paper trading account."""

    name: str = Field(default="Demo Account")
    initial_balance: float = Field(default=100000.0, ge=100.0)


class PaperAccountSchema(BaseModel):
    """Paper trading account response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    initial_balance: float
    current_balance: float
    realized_pnl: float
    unrealized_pnl: float
    currency: str
    is_active: bool


class SubmitPaperOrderRequest(BaseModel):
    """Order placement request schema."""

    account_id: uuid.UUID
    symbol: str
    side: Literal["BUY", "SELL"]
    order_type: Literal["MARKET", "LIMIT", "STOP_LOSS", "TAKE_PROFIT"] = "MARKET"
    quantity: float = Field(..., gt=0.0)
    # LIMIT resting price. Required for LIMIT orders.
    price: float | None = None
    # Trigger level. Required for STOP_LOSS and TAKE_PROFIT orders.
    stop_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None

    @model_validator(mode="after")
    def check_required_prices(self) -> "SubmitPaperOrderRequest":
        """Reject an order whose type needs a price it was not given.

        Catching this at the edge means the fill engine never has to guess what
        an incomplete order meant.
        """
        if self.order_type == "LIMIT" and self.price is None:
            raise ValueError("LIMIT orders require a price")
        if self.order_type in {"STOP_LOSS", "TAKE_PROFIT"} and self.stop_price is None:
            raise ValueError(f"{self.order_type} orders require a stop_price")
        return self


class PaperOrderSchema(BaseModel):
    """Paper order response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float
    stop_price: float | None
    filled_price: float | None
    filled_quantity: float
    status: str
    stop_loss: float | None
    take_profit: float | None


class PaperPositionSchema(BaseModel):
    """Paper position response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    symbol: str
    side: str
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    stop_loss: float | None
    take_profit: float | None
    status: str
