"""Per-fill realised P&L on paper orders.

Revision ID: 008_paper_realized_pnl
Revises: 007_resting_paper_orders
Create Date: 2026-10-30

The daily-loss limit needs today's realised losses per paper account. Each
SELL fill now records its realised P&L and when it filled; a resting order
fills long after it is created, so created_at cannot stand in for fill time.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008_paper_realized_pnl"
down_revision: str | None = "007_resting_paper_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add fill time and realised P&L to paper orders."""
    op.add_column("paper_orders", sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("paper_orders", sa.Column("realized_pnl", sa.Float(), nullable=True))
    # The risk gate sums one account's fills since UTC midnight on every BUY.
    op.create_index("ix_paper_orders_account_filled_at", "paper_orders", ["account_id", "filled_at"])


def downgrade() -> None:
    """Remove per-fill realised P&L."""
    op.drop_index("ix_paper_orders_account_filled_at", table_name="paper_orders")
    op.drop_column("paper_orders", "realized_pnl")
    op.drop_column("paper_orders", "filled_at")
