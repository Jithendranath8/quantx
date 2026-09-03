"""
QuantX — User Repository.

Data access layer for User, RefreshToken, and AuditLog models.
All database operations are performed through async SQLAlchemy sessions.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import AuditLog, RefreshToken, User


class UserRepository:
    """Repository for user CRUD operations.

    Encapsulates all database queries related to the User model.
    Does not contain business logic — that belongs in the service layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        email: str,
        username: str,
        hashed_password: str,
        full_name: str | None = None,
    ) -> User:
        """Create a new user record.

        Args:
            email: Unique email address.
            username: Unique username.
            hashed_password: Pre-hashed password (bcrypt).
            full_name: Optional full name.

        Returns:
            The created User instance.
        """
        user = User(
            email=email.lower().strip(),
            username=username.strip(),
            hashed_password=hashed_password,
            full_name=full_name,
        )
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def get_by_id(self, user_id: str | uuid.UUID) -> User | None:
        """Find a user by their UUID.

        Args:
            user_id: The user's UUID (string or UUID object).

        Returns:
            The User instance or None if not found.
        """
        if isinstance(user_id, str):
            user_id = uuid.UUID(user_id)
        stmt = select(User).where(User.id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Find a user by email address.

        Args:
            email: The email to search for (case-insensitive).

        Returns:
            The User instance or None if not found.
        """
        stmt = select(User).where(User.email == email.lower().strip())
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        """Find a user by username.

        Args:
            username: The username to search for.

        Returns:
            The User instance or None if not found.
        """
        stmt = select(User).where(User.username == username.strip())
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, user_id: str | uuid.UUID, **kwargs: object) -> User | None:
        """Update user fields.

        Args:
            user_id: The user's UUID.
            **kwargs: Fields to update (e.g., full_name="John").

        Returns:
            The updated User instance or None if not found.
        """
        if isinstance(user_id, str):
            user_id = uuid.UUID(user_id)

        kwargs["updated_at"] = datetime.now(UTC)
        stmt = update(User).where(User.id == user_id).values(**kwargs).returning(User)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.scalar_one_or_none()

    async def deactivate(self, user_id: str | uuid.UUID) -> bool:
        """Deactivate a user account.

        Args:
            user_id: The user's UUID.

        Returns:
            True if the user was deactivated.
        """
        user = await self.update(user_id, is_active=False)
        return user is not None

    async def list_users(self, offset: int = 0, limit: int = 50) -> list[User]:
        """List users with pagination.

        Args:
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of User instances.
        """
        stmt = select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        """Count total number of users."""
        from sqlalchemy import func as sa_func

        stmt = select(sa_func.count()).select_from(User)
        result = await self._session.execute(stmt)
        return result.scalar_one()


class RefreshTokenRepository:
    """Repository for refresh token CRUD operations.

    Stores hashed versions of refresh tokens for security.
    Supports token rotation and revocation.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _hash_token(token: str) -> str:
        """Create SHA-256 hash of a refresh token."""
        return hashlib.sha256(token.encode()).hexdigest()

    async def create(
        self,
        user_id: uuid.UUID,
        token: str,
        expires_at: datetime | None = None,
    ) -> RefreshToken:
        """Store a new refresh token (hashed).

        Args:
            user_id: The user's UUID.
            token: The raw refresh token string.
            expires_at: Absolute expiry; defaults to the configured lifetime.

        Returns:
            The created RefreshToken record.
        """
        if expires_at is None:
            settings = get_settings()
            expires_at = datetime.now(UTC) + timedelta(
                days=settings.jwt_refresh_token_expire_days
            )

        refresh = RefreshToken(
            user_id=user_id,
            token_hash=self._hash_token(token),
            expires_at=expires_at,
        )
        self._session.add(refresh)
        await self._session.flush()
        return refresh

    async def find_by_token(self, token: str) -> RefreshToken | None:
        """Find a refresh token record by its raw token value.

        Args:
            token: The raw refresh token string.

        Returns:
            The RefreshToken record or None.
        """
        token_hash = self._hash_token(token)
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.is_revoked.is_(False),
            # Expiry is enforced in the query as well as in the JWT, so a token
            # stays unusable even if the signing key's clock skews.
            RefreshToken.expires_at > datetime.now(UTC),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(self, token: str) -> bool:
        """Revoke a specific refresh token.

        Args:
            token: The raw refresh token string.

        Returns:
            True if the token was found and revoked.
        """
        token_hash = self._hash_token(token)
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .values(is_revoked=True, updated_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0  # type: ignore[union-attr]

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke all refresh tokens for a user (logout everywhere).

        Args:
            user_id: The user's UUID.

        Returns:
            Number of tokens revoked.
        """
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.is_revoked.is_(False),
            )
            .values(is_revoked=True, updated_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount  # type: ignore[union-attr]

    async def cleanup_revoked(self) -> int:
        """Delete all revoked tokens (housekeeping).

        Returns:
            Number of tokens deleted.
        """
        stmt = delete(RefreshToken).where(RefreshToken.is_revoked.is_(True))
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount  # type: ignore[union-attr]

    async def cleanup_expired(self) -> int:
        """Delete tokens whose expiry has passed.

        Returns:
            Number of tokens deleted.
        """
        stmt = delete(RefreshToken).where(RefreshToken.expires_at <= datetime.now(UTC))
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount  # type: ignore[union-attr]


class AuditLogRepository:
    """Repository for audit log operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        action: str,
        user_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: str | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Create an audit log entry.

        Args:
            action: Action identifier (e.g., "user.login").
            user_id: The user who performed the action.
            resource_type: Type of resource affected.
            resource_id: ID of the affected resource.
            details: Additional JSON context.
            ip_address: Client IP address.

        Returns:
            The created AuditLog record.
        """
        entry = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry
