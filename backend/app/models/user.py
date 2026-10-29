"""
QuantX — User ORM Model.

Defines the users table with authentication fields, profile data,
and trading preferences. Uses UUID primary keys for security.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    """User account model.

    Stores authentication credentials, profile information,
    and account status. Passwords are stored as bcrypt hashes.

    Attributes:
        id: UUID primary key.
        email: Unique email address (used for login).
        username: Unique display name.
        hashed_password: Bcrypt password hash.
        full_name: Optional full name.
        is_active: Whether the account is enabled.
        is_superuser: Whether the user has admin privileges.
        bio: Optional biography/description.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        index=True,
        nullable=False,
    )
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    full_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    bio: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    # Set when the account was created through an OAuth provider. Only such
    # accounts accept provider sign-in: registration does not verify email
    # ownership, so a password account may hold an address its owner never
    # proved, and must not be handed to whoever signs in with that address.
    oauth_provider: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        default=None,
    )


class RefreshToken(Base):
    """Stores active refresh tokens for token rotation.

    Each user can have multiple refresh tokens (one per device/session).
    Tokens are deleted on logout or when rotated.

    Attributes:
        id: UUID primary key.
        user_id: FK to the users table.
        token_hash: SHA-256 hash of the refresh token (never store raw).
        expires_at: When this refresh token expires.
        is_revoked: Whether this token has been explicitly revoked.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    # Documented since the first version of this model but never actually
    # stored, which left no way to prune tokens that had simply aged out.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    is_revoked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )


class AuditLog(Base):
    """Audit log for tracking important user and system actions.

    Every significant action (login, trade, settings change) is logged
    for compliance and debugging.

    Attributes:
        id: UUID primary key.
        user_id: The user who performed the action (nullable for system).
        action: The action type (e.g., "user.login", "trade.placed").
        resource_type: The type of resource affected.
        resource_id: The ID of the affected resource.
        details: JSON string with additional context.
        ip_address: Client IP address.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=True,
    )
    action: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )
    resource_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    details: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
    )
