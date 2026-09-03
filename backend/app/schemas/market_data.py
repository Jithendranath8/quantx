"""
QuantX — Market Data Schemas.

Pydantic models for market data REST responses, WebSocket payloads,
and historical download requests.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CandleSchema(BaseModel):
    """OHLCV Candle response schema."""

    model_config = ConfigDict(from_attributes=True)

    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: datetime
    quote_volume: float = 0.0
    trades_count: int = 0
    is_closed: bool = True


class TickerSchema(BaseModel):
    """24h Ticker statistics schema."""

    symbol: str
    price_change: float = Field(..., alias="priceChange")
    price_change_percent: float = Field(..., alias="priceChangePercent")
    last_price: float = Field(..., alias="lastPrice")
    high_price: float = Field(..., alias="highPrice")
    low_price: float = Field(..., alias="lowPrice")
    volume: float = Field(..., alias="volume")
    quote_volume: float = Field(..., alias="quoteVolume")


class OrderbookEntry(BaseModel):
    """Orderbook price & quantity pair."""

    price: float
    quantity: float


class OrderbookSchema(BaseModel):
    """Orderbook depth response schema."""

    symbol: str
    bids: list[OrderbookEntry]
    asks: list[OrderbookEntry]
    last_update_id: int = Field(..., alias="lastUpdateId")


class DownloadHistoryRequest(BaseModel):
    """Request schema for triggering a historical data download task."""

    symbol: str = Field(..., json_schema_extra={"example": "BTCUSDT"})
    timeframe: str = Field(..., json_schema_extra={"example": "1m"})
    days: int = Field(default=30, ge=1, le=365, description="Number of historical days to download")
