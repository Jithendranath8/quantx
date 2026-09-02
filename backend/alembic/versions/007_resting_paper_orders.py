"""Resting paper order types.

Revision ID: 007_resting_paper_orders
Revises: 006_ai_outcome_provenance
Create Date: 2026-09-02

Paper trading previously simulated MARKET fills only. LIMIT, STOP_LOSS and
TAKE_PROFIT orders now rest until the market reaches their level, which needs a
trigger price and an order_type column wide enough to hold "TAKE_PROFIT".
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007_resting_paper_orders"
down_revision: str | None = "006_ai_outcome_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the trigger price and widen order_type."""
    op.add_column("paper_orders", sa.Column("stop_price", sa.Float(), nullable=True))
    # "TAKE_PROFIT" is 11 characters and does not fit in varchar(10).
    op.alter_column(
        "paper_orders", "order_type", type_=sa.String(length=20), existing_nullable=False
    )
    # The fill worker scans for PENDING orders on every tick.
    op.create_index(
        "ix_paper_orders_pending",
        "paper_orders",
        ["symbol"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    """Remove resting-order support."""
    op.drop_index("ix_paper_orders_pending", table_name="paper_orders")
    op.execute("UPDATE paper_orders SET order_type = 'MARKET' WHERE length(order_type) > 10")
    op.alter_column(
        "paper_orders", "order_type", type_=sa.String(length=10), existing_nullable=False
    )
    op.drop_column("paper_orders", "stop_price")
