"""Add master models tables for 40-phase platform upgrade

Revision ID: 004_master_upgrade
Revises: 003_paper_trading
Create Date: 2026-08-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_master_upgrade"
down_revision: str | None = "003_paper_trading"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Event Ledger Table
    op.create_table(
        "event_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", sa.String(64), nullable=False, unique=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("symbol", sa.String(20), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_event_ledger"),
    )
    op.create_index("ix_event_ledger_event_id", "event_ledger", ["event_id"])
    op.create_index("ix_event_ledger_timestamp", "event_ledger", ["timestamp"])
    op.create_index("ix_event_ledger_user_id", "event_ledger", ["user_id"])
    op.create_index("ix_event_ledger_symbol", "event_ledger", ["symbol"])

    # 2. Trade Journal Table
    op.create_table(
        "trade_journals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_id", sa.String(64), nullable=False, unique=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("take_profit", sa.Float(), nullable=True),
        sa.Column("risk_reward", sa.Float(), nullable=True),
        sa.Column("market_structure", sa.String(50), nullable=True),
        sa.Column("indicators_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("orderbook_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("funding_rate", sa.Float(), nullable=True),
        sa.Column("open_interest", sa.Float(), nullable=True),
        sa.Column("liquidations_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ai_reasoning", sa.Text(), nullable=True),
        sa.Column("strategy_signal", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("execution_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("screenshot_url", sa.String(500), nullable=True),
        sa.Column("user_notes", sa.Text(), nullable=True),
        sa.Column("lessons", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_trade_journals"),
    )
    op.create_index("ix_trade_journals_user_id", "trade_journals", ["user_id"])
    op.create_index("ix_trade_journals_trade_id", "trade_journals", ["trade_id"])
    op.create_index("ix_trade_journals_symbol", "trade_journals", ["symbol"])

    # 3. Order Flow Snapshots Table
    op.create_table(
        "order_flow_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bid_ask_imbalance", sa.Float(), nullable=False),
        sa.Column("spread", sa.Float(), nullable=False),
        sa.Column("orderbook_pressure", sa.Float(), nullable=False),
        sa.Column("depth_imbalance", sa.Float(), nullable=False),
        sa.Column("aggressive_buy_vol", sa.Float(), nullable=False),
        sa.Column("aggressive_sell_vol", sa.Float(), nullable=False),
        sa.Column("taker_buy_sell_ratio", sa.Float(), nullable=False),
        sa.Column("volume_delta", sa.Float(), nullable=False),
        sa.Column("liquidity_gaps", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_order_flow_snapshots"),
    )
    op.create_index("ix_order_flow_snapshots_symbol", "order_flow_snapshots", ["symbol"])
    op.create_index("ix_order_flow_snapshots_timestamp", "order_flow_snapshots", ["timestamp"])

    # 4. Liquidation Events Table
    op.create_table(
        "liquidation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("total_value_usd", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_liquidation_events"),
    )
    op.create_index("ix_liquidation_events_symbol", "liquidation_events", ["symbol"])
    op.create_index("ix_liquidation_events_timestamp", "liquidation_events", ["timestamp"])

    # 5. Funding and OI Table
    op.create_table(
        "funding_oi_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("funding_rate", sa.Float(), nullable=False),
        sa.Column("open_interest", sa.Float(), nullable=False),
        sa.Column("oi_change_24h", sa.Float(), nullable=False),
        sa.Column("oi_change_pct", sa.Float(), nullable=False),
        sa.Column("funding_change_24h", sa.Float(), nullable=False),
        sa.Column("signal_interpretation", sa.String(50), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_funding_oi_records"),
    )
    op.create_index("ix_funding_oi_records_symbol", "funding_oi_records", ["symbol"])

    # 6. News Articles Table
    op.create_table(
        "news_articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("headline", sa.String(500), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=False),
        sa.Column("sentiment_label", sa.String(20), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("symbols", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_news_articles"),
    )
    op.create_index("ix_news_articles_event_type", "news_articles", ["event_type"])

    # 7. Persistent Risk State Table
    op.create_table(
        "risk_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("circuit_breaker_active", sa.Boolean(), nullable=False),
        sa.Column("circuit_breaker_reason", sa.String(255), nullable=True),
        sa.Column("daily_loss_usd", sa.Float(), nullable=False),
        sa.Column("peak_portfolio_value", sa.Float(), nullable=False),
        sa.Column("current_drawdown_pct", sa.Float(), nullable=False),
        sa.Column("last_loss_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_risk_state"),
    )
    op.create_index("ix_risk_state_user_id", "risk_state", ["user_id"])

    # 8. Experiment Records Table
    op.create_table(
        "experiment_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("experiment_id", sa.String(64), nullable=False, unique=True),
        sa.Column("strategy_name", sa.String(100), nullable=False),
        sa.Column("strategy_version", sa.String(20), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dataset_version", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("start_date", sa.String(30), nullable=False),
        sa.Column("end_date", sa.String(30), nullable=False),
        sa.Column("fees", sa.Float(), nullable=False),
        sa.Column("slippage", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("ai_model", sa.String(50), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("git_commit", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_experiment_records"),
    )
    op.create_index("ix_experiment_records_experiment_id", "experiment_records", ["experiment_id"])

    # 9. Dataset Fingerprints Table
    op.create_table(
        "dataset_fingerprints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("start_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dataset_fingerprints"),
    )

    # 10. AI Decision Logs Table
    op.create_table(
        "ai_decision_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model", sa.String(50), nullable=False),
        sa.Column("model_version", sa.String(20), nullable=False),
        sa.Column("prompt_version", sa.String(20), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_decision", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("token_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("was_validated", sa.Boolean(), nullable=False),
        sa.Column("validation_rejection_reason", sa.String(255), nullable=True),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ai_decision_logs"),
    )
    op.create_index("ix_ai_decision_logs_timestamp", "ai_decision_logs", ["timestamp"])


def downgrade() -> None:
    op.drop_table("ai_decision_logs")
    op.drop_table("dataset_fingerprints")
    op.drop_table("experiment_records")
    op.drop_table("risk_state")
    op.drop_table("news_articles")
    op.drop_table("funding_oi_records")
    op.drop_table("liquidation_events")
    op.drop_table("order_flow_snapshots")
    op.drop_table("trade_journals")
    op.drop_table("event_ledger")
