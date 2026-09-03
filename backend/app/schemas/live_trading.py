"""
QuantX — Live Trading Schemas.
"""

from typing import Literal

from pydantic import BaseModel, Field


class LiveOrderRequest(BaseModel):
    """Live order submission request."""

    symbol: str = Field(..., json_schema_extra={"example": "BTCUSDT"})
    side: Literal["BUY", "SELL"]
    order_type: Literal["MARKET", "LIMIT", "STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT"] = "LIMIT"
    quantity: float = Field(..., gt=0.0)
    price: float | None = Field(None, description="Limit price")
    stop_price: float | None = Field(None, description="Stop price for stop loss/take profit")
    leverage: int = Field(default=1, ge=1, le=20)


class LiveOrderResponse(BaseModel):
    """Live order execution response."""

    order_id: str
    symbol: str
    side: str
    order_type: str
    status: str
    price: float
    quantity: float
    transact_time: int
