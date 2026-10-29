"""Record which OAuth provider created a user.

Revision ID: 009_user_oauth_provider
Revises: 008_paper_realized_pnl
Create Date: 2026-10-30

OAuth sign-in used to attach to any existing account with the same email.
Password registration does not verify email ownership, so that let someone
pre-register a victim's address and keep password access after the victim
signed in with Google or GitHub. Provider sign-in now reaches only accounts
the provider created.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009_user_oauth_provider"
down_revision: str | None = "008_paper_realized_pnl"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the creating provider to users."""
    op.add_column("users", sa.Column("oauth_provider", sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Remove the creating provider."""
    op.drop_column("users", "oauth_provider")
