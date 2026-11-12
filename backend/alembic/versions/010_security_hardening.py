"""Security hardening: live-trading permission, session families, OAuth subject.

Revision ID: 010_security_hardening
Revises: 009_user_oauth_provider
Create Date: 2026-11-12

Three schema changes behind the 2026-11-12 security audit:

- ``users.can_trade_live``. Every account trades the operator's single exchange
  account and sign-up is open, so placing a live order now needs a permission
  the operator grants explicitly. It defaults to false for everyone, including
  existing accounts: grant it with ``python -m app.cli grant-live-trading``.
- ``refresh_tokens.family_id``. One id per sign-in, carried through rotation and
  named by access tokens, so ending a session also ends its access tokens.
  Existing rows each become their own family.
- ``users.oauth_subject``. The provider's permanent id for the person. Provider
  sign-in is bound to (provider, subject) instead of to a matching email.
  Existing provider accounts bind on their next sign-in.

- ``experiment_records.user_id``. Research experiments were listed to every
  user. New rows record their owner; existing rows have none and are visible
  to superusers only.

It also makes "one open paper position per account and symbol" a database rule.
The fill sweep could create a second open row, after which every later sweep
raised and no user's resting paper orders filled. Duplicates are merged first.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010_security_hardening"
down_revision: str | None = "009_user_oauth_provider"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the security schema changes."""
    op.add_column(
        "users",
        sa.Column("can_trade_live", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("users", sa.Column("oauth_subject", sa.String(length=255), nullable=True))
    op.create_index(
        "uq_users_oauth_identity",
        "users",
        ["oauth_provider", "oauth_subject"],
        unique=True,
        postgresql_where=sa.text("oauth_subject IS NOT NULL"),
    )

    op.add_column("refresh_tokens", sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=True))
    # Each existing token is its own sign-in; gen_random_uuid() is built in
    # from PostgreSQL 13.
    op.execute("UPDATE refresh_tokens SET family_id = gen_random_uuid() WHERE family_id IS NULL")
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    op.add_column("experiment_records", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_experiment_records_user_id", "experiment_records", ["user_id"])

    # Merge duplicate open paper positions into the oldest row (quantity summed,
    # entry price quantity-weighted), then forbid them.
    op.execute(
        """
        WITH ranked AS (
            SELECT id, account_id, symbol, quantity, entry_price,
                   first_value(id) OVER w AS keep_id,
                   sum(quantity) OVER (PARTITION BY account_id, symbol) AS total_qty,
                   sum(quantity * entry_price) OVER (PARTITION BY account_id, symbol) AS total_cost,
                   count(*) OVER (PARTITION BY account_id, symbol) AS n
            FROM paper_positions
            WHERE status = 'OPEN'
            WINDOW w AS (PARTITION BY account_id, symbol ORDER BY created_at, id)
        ),
        merged AS (
            UPDATE paper_positions p
            SET quantity = r.total_qty,
                entry_price = CASE WHEN r.total_qty > 0 THEN r.total_cost / r.total_qty ELSE p.entry_price END
            FROM ranked r
            WHERE p.id = r.keep_id AND r.id = r.keep_id AND r.n > 1
            RETURNING p.id
        )
        DELETE FROM paper_positions p
        USING ranked r
        WHERE p.id = r.id AND r.id <> r.keep_id
        """
    )
    op.create_index(
        "uq_paper_positions_open_account_symbol",
        "paper_positions",
        ["account_id", "symbol"],
        unique=True,
        postgresql_where=sa.text("status = 'OPEN'"),
    )


def downgrade() -> None:
    """Remove the security schema changes."""
    op.drop_index("uq_paper_positions_open_account_symbol", table_name="paper_positions")
    op.drop_index("ix_experiment_records_user_id", table_name="experiment_records")
    op.drop_column("experiment_records", "user_id")
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "family_id")
    op.drop_index("uq_users_oauth_identity", table_name="users")
    op.drop_column("users", "oauth_subject")
    op.drop_column("users", "can_trade_live")
