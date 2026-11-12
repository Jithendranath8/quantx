"""
QuantX — Live Trading Schemas.
"""

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.schemas.validators import Price, Quantity, Symbol


class LiveOrderRequest(BaseModel):
    """Live order submission request."""

    # Bounding the symbol's shape matters beyond tidiness: it is used as a
    # metric label and in log lines, so an arbitrary string would grow the
    # metrics registry without limit.
    symbol: Symbol = Field(..., json_schema_extra={"example": "BTCUSDT"})
    side: Literal["BUY", "SELL"]
    order_type: Literal["MARKET", "LIMIT", "STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT"] = "LIMIT"
    quantity: Quantity
    price: Price | None = Field(None, description="Limit price")
    stop_price: Price | None = Field(None, description="Stop price for stop loss/take profit")
    leverage: int = Field(default=1, ge=1, le=20)

    @model_validator(mode="after")
    def _prices_match_order_type(self) -> Self:
        """Each order type takes exactly the price fields the exchange uses.

        A MARKET order has no price. Accepting one anyway let the caller choose
        the number the risk engine sized the order with, while the exchange
        ignored it and filled at the market.
        """
        if self.order_type == "MARKET":
            if self.price is not None or self.stop_price is not None:
                raise ValueError("MARKET orders take no price or stop_price")
            return self
        if self.price is None:
            raise ValueError(f"{self.order_type} orders require a price")
        if self.order_type in {"STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT"} and self.stop_price is None:
            raise ValueError(f"{self.order_type} orders require a stop_price")
        return self


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
