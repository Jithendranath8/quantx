"""
QuantX — Trade Journal Pydantic Schemas.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CreateJournalEntryRequest(BaseModel):
    symbol: str
    timeframe: str = "1h"
    direction: str  # LONG / SHORT
    entry_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_reward: float | None = None
    market_structure: str | None = None
    indicators_snapshot: dict[str, Any] | None = None
    orderbook_snapshot: dict[str, Any] | None = None
    ai_reasoning: str | None = None
    realized_pnl: float | None = None
    user_notes: str | None = None
    lessons: str | None = None
    tags: list[str] | None = None


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
