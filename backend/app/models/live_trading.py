"""
QuantX — Live Trading ORM Models.

Persists every order actually submitted to the exchange, together with the
exchange's own identifiers and the raw response. Without this table there is no
way to reconcile local intent against exchange state, and no audit trail for
orders that moved real funds.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LiveOrder(Base):
    """An order submitted to (or rejected by) the Binance exchange."""

    __tablename__ = "live_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # Generated locally before the request is sent, and passed to Binance as
    # newClientOrderId. This is the idempotency key: if the HTTP call times out
    # we can query the exchange by this id instead of blindly re-submitting.
    client_order_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    exchange_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    order_type: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="NEW", index=True)
    filled_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    filled_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    commission: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    commission_asset: Mapped[str | None] = mapped_column(String(20), nullable=True)

    is_testnet: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    transact_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_live_orders_user_status", "user_id", "status"),
        Index("ix_live_orders_user_symbol", "user_id", "symbol"),
    )
