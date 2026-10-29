"""
QuantX — Paper Trading ORM Models.

Stores virtual trading accounts, orders, positions, and execution fills.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PaperAccount(Base):
    """Virtual paper trading account model."""

    __tablename__ = "paper_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="Paper Account")
    initial_balance: Mapped[float] = mapped_column(Float, nullable=False, default=100000.0)
    current_balance: Mapped[float] = mapped_column(Float, nullable=False, default=100000.0)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USDT")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)


class PaperOrder(Base):
    """Virtual paper order model."""

    __tablename__ = "paper_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY / SELL
    # 20 chars: TAKE_PROFIT and STOP_LOSS do not fit in 10.
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)  # MARKET / LIMIT / STOP_LOSS / TAKE_PROFIT
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)  # Limit price or reference price
    # Trigger level for STOP_LOSS / TAKE_PROFIT orders.
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    filled_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    filled_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 30 chars, not 20: the kill switch writes "CANCELLED_BY_KILL_SWITCH" (24),
    # which overflowed varchar(20) and failed the whole cancellation statement.
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")  # PENDING, FILLED, CANCELLED, REJECTED, CANCELLED_BY_KILL_SWITCH
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Set when the order fills. realized_pnl is recorded on SELL fills only and
    # is what the daily-loss limit sums over the current UTC day.
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)


class PaperPosition(Base):
    """Virtual paper position model."""

    __tablename__ = "paper_positions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # LONG / SHORT
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[float] = mapped_column(Float, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")  # OPEN, CLOSED
