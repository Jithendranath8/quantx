"""Operational hardening: live orders, timestamps, token expiry, index cleanup.

Revision ID: 005_operational_hardening
Revises: 004_master_upgrade
Create Date: 2026-09-01

Adds:
- live_orders: persists every order submitted to the exchange, keyed by a
  locally generated client_order_id so an indeterminate submit is recoverable.
- refresh_tokens.expires_at: documented on the model since day one but never
  stored, leaving no way to prune aged-out tokens.
- refresh_tokens FK to users with ON DELETE CASCADE, preventing orphan rows.
- ai_decision_logs.user_id / .symbol: attribution for per-user analytics.

Repairs:
- Missing created_at/updated_at on the ten tables migration 004 created without
  them. Every model inherits those columns from Base, so INSERTs into
  event_ledger, ai_decision_logs, trade_journals, risk_state and the rest
  failed with UndefinedColumn: those tables were unwritable.
- Naive TIMESTAMP columns holding timezone-aware values. asyncpg refuses to
  bind an aware datetime into a naive column, so those writes failed too.

Removes:
- Redundant single-column indexes on candles, funding_rates and open_interests.
  Each table already has a composite index with the same leading column, so
  these are never chosen by the planner and only add write amplification. At
  ~4.2M candles/year that is significant index churn for no read benefit.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_operational_hardening"
down_revision: str | None = "004_master_upgrade"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables that inherit Base and therefore require created_at / updated_at.
BASE_TIMESTAMP_TABLES: tuple[str, ...] = (
    "users",
    "refresh_tokens",
    "audit_logs",
    "candles",
    "funding_rates",
    "open_interests",
    "paper_accounts",
    "paper_orders",
    "paper_positions",
    "event_ledger",
    "trade_journals",
    "order_flow_snapshots",
    "liquidation_events",
    "funding_oi_records",
    "news_articles",
    "risk_state",
    "experiment_records",
    "dataset_fingerprints",
    "ai_decision_logs",
    "live_orders",
)

REDUNDANT_INDEXES: tuple[str, ...] = (
    "ix_candles_symbol",
    "ix_candles_timeframe",
    "ix_candles_timestamp",
    "ix_funding_rates_symbol",
    "ix_open_interests_symbol",
)

CONVERT_TO_TIMESTAMPTZ = """
DO $do$
DECLARE r RECORD;
BEGIN
    FOR r IN
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND data_type = 'timestamp without time zone'
    LOOP
        EXECUTE format(
            'ALTER TABLE %I ALTER COLUMN %I TYPE TIMESTAMPTZ USING %I AT TIME ZONE $tz$UTC$tz$',
            r.table_name, r.column_name, r.column_name
        );
    END LOOP;
END $do$;
"""

CONVERT_TO_NAIVE = """
DO $do$
DECLARE r RECORD;
BEGIN
    FOR r IN
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND data_type = 'timestamp with time zone'
    LOOP
        EXECUTE format(
            'ALTER TABLE %I ALTER COLUMN %I TYPE TIMESTAMP USING %I AT TIME ZONE $tz$UTC$tz$',
            r.table_name, r.column_name, r.column_name
        );
    END LOOP;
END $do$;
"""


def upgrade() -> None:
    """Apply the hardening changes."""
    # ── live_orders ──────────────────────────────────────────────────
    op.create_table(
        "live_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_order_id", sa.String(length=64), nullable=False),
        sa.Column("exchange_order_id", sa.String(length=64), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("side", sa.String(length=10), nullable=False),
        sa.Column("order_type", sa.String(length=30), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("stop_price", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="NEW"),
        sa.Column("filled_quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("filled_price", sa.Float(), nullable=True),
        sa.Column("commission", sa.Float(), nullable=False, server_default="0"),
        sa.Column("commission_asset", sa.String(length=20), nullable=True),
        sa.Column("is_testnet", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        sa.Column("raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("transact_time", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_live_orders"),
        sa.UniqueConstraint("client_order_id", name="uq_live_orders_client_order_id"),
    )
    op.create_index("ix_live_orders_user_id", "live_orders", ["user_id"])
    op.create_index("ix_live_orders_client_order_id", "live_orders", ["client_order_id"])
    op.create_index("ix_live_orders_exchange_order_id", "live_orders", ["exchange_order_id"])
    op.create_index("ix_live_orders_symbol", "live_orders", ["symbol"])
    op.create_index("ix_live_orders_status", "live_orders", ["status"])
    op.create_index("ix_live_orders_user_status", "live_orders", ["user_id", "status"])
    op.create_index("ix_live_orders_user_symbol", "live_orders", ["user_id", "symbol"])

    # ── Reconcile Base timestamp columns ─────────────────────────────
    for table in BASE_TIMESTAMP_TABLES:
        for column in ("created_at", "updated_at"):
            op.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} "
                "TIMESTAMPTZ NOT NULL DEFAULT NOW()"
            )

    # ── refresh_tokens.expires_at ────────────────────────────────────
    # Added nullable, backfilled, then made NOT NULL so this works against a
    # table that already holds rows.
    op.add_column(
        "refresh_tokens",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE refresh_tokens SET expires_at = :default WHERE expires_at IS NULL"
        ).bindparams(default=datetime.now(UTC) + timedelta(days=7))
    )
    op.alter_column("refresh_tokens", "expires_at", nullable=False)
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])

    op.execute("DELETE FROM refresh_tokens WHERE user_id NOT IN (SELECT id FROM users)")
    op.create_foreign_key(
        "fk_refresh_tokens_user_id_users",
        "refresh_tokens",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ── ai_decision_logs attribution ─────────────────────────────────
    op.add_column(
        "ai_decision_logs",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_decision_logs",
        sa.Column("symbol", sa.String(length=20), nullable=True),
    )
    op.create_index("ix_ai_decision_logs_user_id", "ai_decision_logs", ["user_id"])
    op.create_index("ix_ai_decision_logs_symbol", "ai_decision_logs", ["symbol"])
    op.create_index(
        "ix_ai_decision_logs_user_time", "ai_decision_logs", ["user_id", "timestamp"]
    )

    # ── Widen paper order/position status ────────────────────────────
    # The kill switch writes "CANCELLED_BY_KILL_SWITCH" (24 chars), which does
    # not fit varchar(20); the cancellation statement failed outright.
    op.alter_column(
        "paper_orders", "status", type_=sa.String(length=30), existing_nullable=False
    )
    op.alter_column(
        "paper_positions", "status", type_=sa.String(length=30), existing_nullable=False
    )

    # ── Naive timestamps -> timestamptz (values read as UTC) ─────────
    op.execute(CONVERT_TO_TIMESTAMPTZ)

    # ── Drop redundant leading-column indexes ────────────────────────
    for index_name in REDUNDANT_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")


def downgrade() -> None:
    """Revert the hardening changes."""
    op.create_index("ix_open_interests_symbol", "open_interests", ["symbol"])
    op.create_index("ix_funding_rates_symbol", "funding_rates", ["symbol"])
    op.create_index("ix_candles_timestamp", "candles", ["timestamp"])
    op.create_index("ix_candles_timeframe", "candles", ["timeframe"])
    op.create_index("ix_candles_symbol", "candles", ["symbol"])

    op.execute(CONVERT_TO_NAIVE)

    op.alter_column(
        "paper_positions", "status", type_=sa.String(length=20), existing_nullable=False
    )
    op.alter_column(
        "paper_orders", "status", type_=sa.String(length=20), existing_nullable=False
    )

    op.drop_index("ix_ai_decision_logs_user_time", table_name="ai_decision_logs")
    op.drop_index("ix_ai_decision_logs_symbol", table_name="ai_decision_logs")
    op.drop_index("ix_ai_decision_logs_user_id", table_name="ai_decision_logs")
    op.drop_column("ai_decision_logs", "symbol")
    op.drop_column("ai_decision_logs", "user_id")

    op.drop_constraint("fk_refresh_tokens_user_id_users", "refresh_tokens", type_="foreignkey")
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "expires_at")

    op.drop_table("live_orders")
