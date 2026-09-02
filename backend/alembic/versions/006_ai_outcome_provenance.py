"""AI decision outcome provenance and experiment reproducibility.

Revision ID: 006_ai_outcome_provenance
Revises: 005_operational_hardening
Create Date: 2026-09-02

Adds:
- ai_decision_logs.outcome_source / .outcome_detail / .settled_at, so a
  hypothetical forward-test result can never be mistaken for money actually
  made or lost. Win rate and expectancy were previously null because nothing
  ever settled a decision; settling them without recording provenance would
  have been worse than leaving them null.
- experiment_records.git_commit and .dataset_row_count, so a recorded
  experiment identifies the code and the data volume it ran against.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006_ai_outcome_provenance"
down_revision: str | None = "005_operational_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add outcome provenance and experiment reproducibility columns."""
    op.add_column(
        "ai_decision_logs",
        sa.Column("outcome_source", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "ai_decision_logs",
        sa.Column("outcome_detail", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "ai_decision_logs",
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Settlement scans for decisions that have no outcome yet.
    op.create_index(
        "ix_ai_decision_logs_unsettled",
        "ai_decision_logs",
        ["timestamp"],
        postgresql_where=sa.text("realized_pnl IS NULL"),
    )

    op.execute(
        "ALTER TABLE experiment_records ADD COLUMN IF NOT EXISTS git_commit VARCHAR(40)"
    )
    op.execute(
        "ALTER TABLE experiment_records ADD COLUMN IF NOT EXISTS dataset_row_count INTEGER"
    )


def downgrade() -> None:
    """Remove the provenance columns."""
    op.execute("ALTER TABLE experiment_records DROP COLUMN IF EXISTS dataset_row_count")
    op.execute("ALTER TABLE experiment_records DROP COLUMN IF EXISTS git_commit")

    op.drop_index("ix_ai_decision_logs_unsettled", table_name="ai_decision_logs")
    op.drop_column("ai_decision_logs", "settled_at")
    op.drop_column("ai_decision_logs", "outcome_detail")
    op.drop_column("ai_decision_logs", "outcome_source")
