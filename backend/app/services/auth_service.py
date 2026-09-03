"""
QuantX — Authentication Service.

Business logic for user registration, login, token refresh, and logout.
Orchestrates between repositories and security utilities.
"""

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    ConflictError,
    InvalidCredentialsError,
    NotFoundError,
    TokenInvalidError,
    ValidationError,
)
from app.core.logging import get_logger
from app.core.security import (
    MAX_PASSWORD_BYTES,
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_refresh_token,
)
from app.models.user import User
from app.repositories.user_repository import (
    AuditLogRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.schemas.auth import (
    AuthResponse,
    MessageResponse,
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
)

logger = get_logger(__name__)
settings = get_settings()

# Computed once at import so the not-found login path costs a verify, not a hash.
_DUMMY_PASSWORD_HASH = hash_password("quantx-timing-equalization-placeholder")


class AuthService:
    """Authentication business logic service.

    Handles registration, login, token refresh, and logout.
    All business rules and validation are enforced here.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._user_repo = UserRepository(session)
        self._token_repo = RefreshTokenRepository(session)
        self._audit_repo = AuditLogRepository(session)

    async def register(
        self,
        data: UserRegisterRequest,
        ip_address: str | None = None,
    ) -> AuthResponse:
        """Register a new user account.

        Validates uniqueness of email and username, creates the user,
        generates tokens, and logs the registration.

        Args:
            data: Registration request data.
            ip_address: Client IP for audit logging.

        Returns:
            AuthResponse with user data and tokens.

        Raises:
            ConflictError: If email or username is already taken.
            ValidationError: If password doesn't meet requirements.
        """
        # Validate password strength
        self._validate_password(data.password)

        # Check for existing email
        existing = await self._user_repo.get_by_email(data.email)
        if existing:
            raise ConflictError("User", "email", data.email)

        # Check for existing username
        existing = await self._user_repo.get_by_username(data.username)
        if existing:
            raise ConflictError("User", "username", data.username)

        # Create user
        hashed_pw = hash_password(data.password)
        user = await self._user_repo.create(
            email=data.email,
            username=data.username,
            hashed_password=hashed_pw,
            full_name=data.full_name,
        )

        # Generate tokens
        tokens = await self._create_tokens(user)

        # Audit log
        await self._audit_repo.log(
            action="user.registered",
            user_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
            ip_address=ip_address,
        )

        await self._session.commit()

        logger.info("user_registered", user_id=str(user.id), email=user.email)

        return AuthResponse(
            user=UserResponse.model_validate(user),
            tokens=tokens,
        )

    async def login(
        self,
        email: str,
        password: str,
        ip_address: str | None = None,
    ) -> AuthResponse:
        """Authenticate a user with email and password.

        Args:
            email: User's email address.
            password: User's plaintext password.
            ip_address: Client IP for audit logging.

        Returns:
            AuthResponse with user data and tokens.

        Raises:
            InvalidCredentialsError: If email/password is wrong.
        """
        user = await self._user_repo.get_by_email(email)
        if user is None:
            # Equalize timing against a fixed, pre-computed hash. The previous
            # code called hash_password() here, generating a brand-new bcrypt
            # hash (12 rounds, ~250ms of CPU) that nothing ever read -- making
            # an unauthenticated endpoint a CPU-exhaustion lever.
            verify_password(password, _DUMMY_PASSWORD_HASH)
            raise InvalidCredentialsError()

        if not verify_password(password, user.hashed_password):
            await self._audit_repo.log(
                action="user.login_failed",
                user_id=user.id,
                details=json.dumps({"reason": "invalid_password"}),
                ip_address=ip_address,
            )
            await self._session.commit()
            raise InvalidCredentialsError()

        if not user.is_active:
            raise InvalidCredentialsError("Account is deactivated")

        # Generate tokens
        tokens = await self._create_tokens(user)

        # Audit log
        await self._audit_repo.log(
            action="user.login",
            user_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
            ip_address=ip_address,
        )

        await self._session.commit()

        logger.info("user_logged_in", user_id=str(user.id))

        return AuthResponse(
            user=UserResponse.model_validate(user),
            tokens=tokens,
        )

    async def refresh_tokens(
        self,
        refresh_token: str,
        ip_address: str | None = None,
    ) -> TokenResponse:
        """Refresh an access token using a valid refresh token.

        Implements token rotation: the old refresh token is revoked
        and a new one is issued.

        Args:
            refresh_token: The current refresh token.
            ip_address: Client IP for audit logging.

        Returns:
            New TokenResponse with fresh access and refresh tokens.

        Raises:
            TokenInvalidError: If the refresh token is invalid or revoked.
        """
        # Verify the JWT signature and claims
        try:
            user_id = verify_refresh_token(refresh_token)
        except Exception as e:
            raise TokenInvalidError() from e

        # Check if token exists and is not revoked
        stored_token = await self._token_repo.find_by_token(refresh_token)
        if stored_token is None:
            logger.warning("refresh_token_reuse_detected", user_id=user_id)
            # Potential token reuse — revoke all tokens for safety
            await self._token_repo.revoke_all_for_user(uuid.UUID(user_id))
            await self._session.commit()
            raise TokenInvalidError("Refresh token has been revoked")

        # Verify user still exists and is active
        user = await self._user_repo.get_by_id(user_id)
        if user is None or not user.is_active:
            raise TokenInvalidError("User not found or deactivated")

        # Revoke the old refresh token (rotation)
        await self._token_repo.revoke(refresh_token)

        # Generate new tokens
        tokens = await self._create_tokens(user)

        await self._audit_repo.log(
            action="user.token_refreshed",
            user_id=user.id,
            ip_address=ip_address,
        )

        await self._session.commit()

        return tokens

    async def logout(
        self,
        refresh_token: str,
        user_id: str,
        ip_address: str | None = None,
    ) -> MessageResponse:
        """Logout by revoking the provided refresh token.

        Args:
            refresh_token: The refresh token to revoke.
            user_id: The authenticated user's ID.
            ip_address: Client IP for audit logging.

        Returns:
            Success message.
        """
        await self._token_repo.revoke(refresh_token)

        await self._audit_repo.log(
            action="user.logout",
            user_id=uuid.UUID(user_id),
            ip_address=ip_address,
        )

        await self._session.commit()

        logger.info("user_logged_out", user_id=user_id)
        return MessageResponse(message="Successfully logged out")

    async def logout_all(
        self,
        user_id: str,
        ip_address: str | None = None,
    ) -> MessageResponse:
        """Logout from all devices by revoking all refresh tokens.

        Args:
            user_id: The authenticated user's ID.
            ip_address: Client IP for audit logging.

        Returns:
            Success message with count of revoked sessions.
        """
        count = await self._token_repo.revoke_all_for_user(uuid.UUID(user_id))

        await self._audit_repo.log(
            action="user.logout_all",
            user_id=uuid.UUID(user_id),
            details=json.dumps({"sessions_revoked": count}),
            ip_address=ip_address,
        )

        await self._session.commit()

        logger.info("user_logged_out_all", user_id=user_id, sessions_revoked=count)
        return MessageResponse(message=f"Logged out from {count} sessions")

    async def get_user(self, user_id: str) -> UserResponse:
        """Get user profile by ID.

        Args:
            user_id: The user's UUID string.

        Returns:
            UserResponse with profile data.

        Raises:
            NotFoundError: If the user does not exist.
        """
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User", user_id)
        return UserResponse.model_validate(user)

    # ── Private Helpers ──────────────────────────────────────────────

    async def _create_tokens(self, user: User) -> TokenResponse:
        """Generate access + refresh tokens and store refresh token hash.

        Args:
            user: The User model instance.

        Returns:
            TokenResponse with both tokens.
        """
        access_token = create_access_token(
            subject=str(user.id),
            extra_claims={"email": user.email, "username": user.username},
        )
        refresh_token = create_refresh_token(subject=str(user.id))

        # Store refresh token hash in database
        await self._token_repo.create(user.id, refresh_token)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )

    @staticmethod
    def _validate_password(password: str) -> None:
        """Enforce password strength requirements.

        Rules:
        - Minimum 8 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit

        Raises:
            ValidationError: If password is too weak.
        """
        errors = []
        if len(password) < 8:
            errors.append("Password must be at least 8 characters")
        if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
            errors.append(
                f"Password must be at most {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded"
            )
        if not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in password):
            errors.append("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one digit")

        if errors:
            # The reasons go in the message as well as the details, so a client
            # that only surfaces `message` still tells the user what to fix.
            raise ValidationError(
                "Password does not meet requirements: " + "; ".join(errors),
                errors,
            )
