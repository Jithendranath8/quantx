"""
QuantX — Trade Journal Pydantic Schemas.
"""

import json
import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.validators import Price, Symbol, Timeframe

# Journal text is stored and shown back to its author; these bounds only stop
# one request from storing megabytes.
_NOTE = 10_000
_SNAPSHOT_BYTES = 50_000


class CreateJournalEntryRequest(BaseModel):
    symbol: Symbol
    timeframe: Timeframe = "1h"
    direction: str = Field(..., pattern=r"^(LONG|SHORT)$")
    entry_price: Price
    stop_loss: Price | None = None
    take_profit: Price | None = None
    risk_reward: float | None = Field(None, allow_inf_nan=False, ge=-1e6, le=1e6)
    market_structure: str | None = Field(None, max_length=_NOTE)
    indicators_snapshot: dict[str, Any] | None = None
    orderbook_snapshot: dict[str, Any] | None = None
    ai_reasoning: str | None = Field(None, max_length=_NOTE)
    realized_pnl: float | None = Field(None, allow_inf_nan=False, ge=-1e15, le=1e15)
    user_notes: str | None = Field(None, max_length=_NOTE)
    lessons: str | None = Field(None, max_length=_NOTE)
    tags: list[Annotated[str, Field(max_length=50)]] | None = Field(None, max_length=30)

    @field_validator("indicators_snapshot", "orderbook_snapshot")
    @classmethod
    def _snapshot_is_small(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """A snapshot is a few dozen numbers, not an arbitrary document."""
        if value is not None and len(json.dumps(value, default=str)) > _SNAPSHOT_BYTES:
            raise ValueError(f"snapshot is larger than {_SNAPSHOT_BYTES} bytes")
        return value


class JournalEntrySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trade_id: str
    symbol: str
    timeframe: str
    direction: str
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    risk_reward: float | None
    market_structure: str | None
    ai_reasoning: str | None
    realized_pnl: float | None
    user_notes: str | None
    lessons: str | None
    tags: list[str] | None
    created_at: datetime
