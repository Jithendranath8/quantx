"""Add market data tables (candles, funding_rates, open_interests)

Revision ID: 002_market_data
Revises: 001_initial
Create Date: 2026-08-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002_market_data"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Candles table ────────────────────────────────────────────────
    op.create_table(
        "candles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("close_time", sa.DateTime(), nullable=False),
        sa.Column("quote_volume", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("trades_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_candles"),
    )
    op.create_index("ix_candles_symbol", "candles", ["symbol"])
    op.create_index("ix_candles_timeframe", "candles", ["timeframe"])
    op.create_index("ix_candles_timestamp", "candles", ["timestamp"])
    op.create_index(
        "ix_candles_symbol_tf_time",
        "candles",
        ["symbol", "timeframe", "timestamp"],
        unique=True,
    )

    # ── Funding Rates table ──────────────────────────────────────────
    op.create_table(
        "funding_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_funding_rates"),
    )
    op.create_index("ix_funding_rates_symbol", "funding_rates", ["symbol"])
    op.create_index("ix_funding_rates_timestamp", "funding_rates", ["timestamp"])
    op.create_index(
        "ix_funding_rates_symbol_time",
        "funding_rates",
        ["symbol", "timestamp"],
        unique=True,
    )

    # ── Open Interests table ─────────────────────────────────────────
    op.create_table(
        "open_interests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("open_interest", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_open_interests"),
    )
    op.create_index("ix_open_interests_symbol", "open_interests", ["symbol"])
    op.create_index("ix_open_interests_timestamp", "open_interests", ["timestamp"])
    op.create_index(
        "ix_open_interests_symbol_time",
        "open_interests",
        ["symbol", "timestamp"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("open_interests")
    op.drop_table("funding_rates")
    op.drop_table("candles")
