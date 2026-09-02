"""
QuantX — Market Data ORM Models.

Stores OHLCV candles, funding rates, open interest, and symbol metadata in PostgreSQL.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Candle(Base):
    """OHLCV Candlestick data model.

    Stores historical and live candlestick data partitioned/indexed by symbol,
    timeframe, and timestamp.
    """

    __tablename__ = "candles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )
    timeframe: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    close_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quote_volume: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    trades_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    is_closed: Mapped[bool] = mapped_column(nullable=False, default=True)

    __table_args__ = (
        Index("ix_candles_symbol_tf_time", "symbol", "timeframe", "timestamp", unique=True),
    )


class FundingRate(Base):
    """Perpetual Futures Funding Rate model."""

    __tablename__ = "funding_rates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    rate: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    __table_args__ = (
        Index("ix_funding_rates_symbol_time", "symbol", "timestamp", unique=True),
    )


class OpenInterest(Base):
    """Perpetual Futures Open Interest model."""

    __tablename__ = "open_interests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    open_interest: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    __table_args__ = (
        Index("ix_open_interests_symbol_time", "symbol", "timestamp", unique=True),
    )
