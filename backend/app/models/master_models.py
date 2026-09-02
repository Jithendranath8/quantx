"""
QuantX — Comprehensive Database Models for Master 40-Phase Architecture.

Includes:
- EventLedger (Immutable Event Trail)
- TradeJournal (Trade Journal with Snapshots & Lessons)
- OrderFlowSnapshot (Bid/Ask Imbalance, Book Pressure)
- LiquidationEvent (Long/Short Liquidations Data)
- FundingAndOIRecord (Funding Rate & Open Interest Tracking)
- NewsArticle (News & Macro Intelligence)
- RiskState (Persistent Risk & Circuit Breaker State)
- ExperimentRecord (Research Experiment Registry)
- DatasetFingerprint (Dataset Versioning & Hashes)
- AIDecisionLog (AI Observability & Decision Metrics)
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EventLedger(Base):
    """Central immutable event ledger for complete platform auditability."""

    __tablename__ = "event_ledger"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    symbol: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class TradeJournal(Base):
    """Trade Journal model for comprehensive trade analysis and notes."""

    __tablename__ = "trade_journals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    trade_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # LONG / SHORT
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_reward: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_structure: Mapped[str | None] = mapped_column(String(50), nullable=True)
    indicators_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    orderbook_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    funding_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    open_interest: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidations_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ai_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    strategy_signal: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    execution_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    screenshot_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    lessons: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class OrderFlowSnapshot(Base):
    """Order Flow analytics snapshot model."""

    __tablename__ = "order_flow_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)
    bid_ask_imbalance: Mapped[float] = mapped_column(Float, nullable=False)
    spread: Mapped[float] = mapped_column(Float, nullable=False)
    orderbook_pressure: Mapped[float] = mapped_column(Float, nullable=False)
    depth_imbalance: Mapped[float] = mapped_column(Float, nullable=False)
    aggressive_buy_vol: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    aggressive_sell_vol: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    taker_buy_sell_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    volume_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    liquidity_gaps: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class LiquidationEvent(Base):
    """Real liquidation event model."""

    __tablename__ = "liquidation_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY / SELL (position liquidated)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    total_value_usd: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)


class FundingAndOIRecord(Base):
    """Funding Rate and Open Interest tracking model."""

    __tablename__ = "funding_oi_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    funding_rate: Mapped[float] = mapped_column(Float, nullable=False)
    open_interest: Mapped[float] = mapped_column(Float, nullable=False)
    oi_change_24h: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    oi_change_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    funding_change_24h: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    signal_interpretation: Mapped[str] = mapped_column(String(50), nullable=False, default="NEUTRAL")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)


class NewsArticle(Base):
    """News & Macro Intelligence model."""

    __tablename__ = "news_articles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # -1.0 to +1.0
    sentiment_label: Mapped[str] = mapped_column(String(20), nullable=False, default="NEUTRAL")  # BULLISH / BEARISH / NEUTRAL
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # CPI, FOMC, FED, REGULATION, ETC
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    symbols: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class RiskState(Base):
    """Persistent Risk Engine state model."""

    __tablename__ = "risk_state"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    circuit_breaker_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    circuit_breaker_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    daily_loss_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    peak_portfolio_value: Mapped[float] = mapped_column(Float, nullable=False, default=100000.0)
    current_drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_loss_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class ExperimentRecord(Base):
    """Research Experiment Registry model."""

    __tablename__ = "experiment_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    experiment_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    strategy_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    strategy_version: Mapped[str] = mapped_column(String(20), nullable=False, default="v1.0")
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    start_date: Mapped[str] = mapped_column(String(30), nullable=False)
    end_date: Mapped[str] = mapped_column(String(30), nullable=False)
    fees: Mapped[float] = mapped_column(Float, nullable=False)
    slippage: Mapped[float] = mapped_column(Float, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    git_commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Row count behind dataset_version, so two runs sharing a fingerprint can
    # be confirmed to have seen the same amount of data.
    dataset_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class DatasetFingerprint(Base):
    """Dataset versioning and fingerprint hash model."""

    __tablename__ = "dataset_fingerprints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    dataset_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    start_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class AIDecisionLog(Base):
    """AI Observability decision tracking model."""

    __tablename__ = "ai_decision_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    symbol: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    input_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output_decision: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    token_usage: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    was_validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    validation_rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # PnL attributed to this decision, per SETTLEMENT_NOTIONAL_USD of notional.
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    # How that number was obtained. Without this a hypothetical forward-test
    # result is indistinguishable from money actually made or lost, which is
    # exactly the ambiguity that makes a performance metric untrustworthy.
    outcome_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    outcome_detail: Mapped[str | None] = mapped_column(String(50), nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)

    __table_args__ = (
        Index("ix_ai_decision_logs_user_time", "user_id", "timestamp"),
    )
