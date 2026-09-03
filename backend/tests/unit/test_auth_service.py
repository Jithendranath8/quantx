"""
QuantX — Unit Tests for Authentication Service.

Tests business logic in AuthService without hitting the actual database.
Uses the test database fixtures from conftest.py.
"""

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    InvalidCredentialsError,
    ValidationError,
)
from app.schemas.auth import UserRegisterRequest
from app.services.auth_service import AuthService


@pytest.mark.unit
class TestAuthServiceRegister:
    """Tests for AuthService.register()."""

    @pytest.mark.asyncio
    async def test_register_success(self, db_session: AsyncSession) -> None:
        """Successful registration should return user and tokens."""
        service = AuthService(db_session)
        data = UserRegisterRequest(
            email="newuser@quantx.io",
            username="newuser",
            password="StrongP@ss1",
            full_name="New User",
        )

        result = await service.register(data)

        assert result.user.email == "newuser@quantx.io"
        assert result.user.username == "newuser"
        assert result.user.full_name == "New User"
        assert result.user.is_active is True
        assert result.user.is_superuser is False
        assert result.tokens.access_token
        assert result.tokens.refresh_token
        assert result.tokens.token_type == "bearer"

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, db_session: AsyncSession) -> None:
        """Registration with existing email should raise ConflictError."""
        service = AuthService(db_session)
        data = UserRegisterRequest(
            email="dupe@quantx.io",
            username="user1",
            password="StrongP@ss1",
        )
        await service.register(data)

        data2 = UserRegisterRequest(
            email="dupe@quantx.io",
            username="user2",
            password="StrongP@ss1",
        )
        with pytest.raises(ConflictError, match="email"):
            await service.register(data2)

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, db_session: AsyncSession) -> None:
        """Registration with existing username should raise ConflictError."""
        service = AuthService(db_session)
        data = UserRegisterRequest(
            email="first@quantx.io",
            username="sameuser",
            password="StrongP@ss1",
        )
        await service.register(data)

        data2 = UserRegisterRequest(
            email="second@quantx.io",
            username="sameuser",
            password="StrongP@ss1",
        )
        with pytest.raises(ConflictError, match="username"):
            await service.register(data2)

    def test_short_password_rejected_by_schema(self) -> None:
        """A password under 8 characters is rejected at the schema boundary."""
        with pytest.raises(PydanticValidationError):
            UserRegisterRequest(
                email="weak@quantx.io", username="weakuser", password="short"
            )

    def test_overlong_password_rejected_by_schema(self) -> None:
        """A password past bcrypt's 72-byte limit is rejected rather than truncated."""
        with pytest.raises(PydanticValidationError):
            UserRegisterRequest(
                email="long@quantx.io", username="longuser", password="A1" + "x" * 100
            )

    @pytest.mark.asyncio
    async def test_register_password_without_digit(self, db_session: AsyncSession) -> None:
        """A password with no digit is rejected by the domain policy."""
        service = AuthService(db_session)
        data = UserRegisterRequest(
            email="nodigit@quantx.io",
            username="nodigituser",
            password="NoDigitsHere",
        )
        with pytest.raises(ValidationError, match="digit"):
            await service.register(data)

    @pytest.mark.asyncio
    async def test_register_no_uppercase(self, db_session: AsyncSession) -> None:
        """Password without uppercase should raise ValidationError."""
        service = AuthService(db_session)
        data = UserRegisterRequest(
            email="noup@quantx.io",
            username="noupuser",
            password="alllowercase1",
        )
        with pytest.raises(ValidationError, match="uppercase"):
            await service.register(data)


@pytest.mark.unit
class TestAuthServiceLogin:
    """Tests for AuthService.login()."""

    @pytest.mark.asyncio
    async def test_login_success(self, db_session: AsyncSession) -> None:
        """Login with correct credentials should return tokens."""
        service = AuthService(db_session)
        # First register
        reg_data = UserRegisterRequest(
            email="logintest@quantx.io",
            username="logintest",
            password="StrongP@ss1",
        )
        await service.register(reg_data)

        # Then login
        result = await service.login("logintest@quantx.io", "StrongP@ss1")
        assert result.user.email == "logintest@quantx.io"
        assert result.tokens.access_token

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, db_session: AsyncSession) -> None:
        """Login with wrong password should raise InvalidCredentialsError."""
        service = AuthService(db_session)
        reg_data = UserRegisterRequest(
            email="wrongpw@quantx.io",
            username="wrongpw",
            password="StrongP@ss1",
        )
        await service.register(reg_data)

        with pytest.raises(InvalidCredentialsError):
            await service.login("wrongpw@quantx.io", "WrongPassword1")

    @pytest.mark.asyncio
    async def test_login_nonexistent_email(self, db_session: AsyncSession) -> None:
        """Login with non-existent email should raise InvalidCredentialsError."""
        service = AuthService(db_session)
        with pytest.raises(InvalidCredentialsError):
            await service.login("nobody@quantx.io", "AnyPassword1")

    @pytest.mark.asyncio
    async def test_login_email_case_insensitive(self, db_session: AsyncSession) -> None:
        """Login should be case-insensitive for email."""
        service = AuthService(db_session)
        reg_data = UserRegisterRequest(
            email="CasE@quantx.io",
            username="casetest",
            password="StrongP@ss1",
        )
        await service.register(reg_data)

        # Login with different case
        result = await service.login("case@quantx.io", "StrongP@ss1")
        assert result.user.email == "case@quantx.io"


@pytest.mark.unit
class TestAuthServiceTokenRefresh:
    """Tests for AuthService.refresh_tokens()."""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, db_session: AsyncSession) -> None:
        """Valid refresh token should return new token pair."""
        service = AuthService(db_session)
        reg_data = UserRegisterRequest(
            email="refresh@quantx.io",
            username="refreshuser",
            password="StrongP@ss1",
        )
        auth_response = await service.register(reg_data)
        old_refresh = auth_response.tokens.refresh_token

        # Refresh tokens
        new_tokens = await service.refresh_tokens(old_refresh)
        assert new_tokens.access_token
        assert new_tokens.refresh_token
        assert new_tokens.refresh_token != old_refresh  # Rotation

    @pytest.mark.asyncio
    async def test_refresh_token_reuse_detected(self, db_session: AsyncSession) -> None:
        """Reusing a revoked refresh token should fail and revoke all tokens."""
        from app.core.exceptions import TokenInvalidError

        service = AuthService(db_session)
        reg_data = UserRegisterRequest(
            email="reuse@quantx.io",
            username="reuseuser",
            password="StrongP@ss1",
        )
        auth_response = await service.register(reg_data)
        old_refresh = auth_response.tokens.refresh_token

        # Use the refresh token (rotates it)
        await service.refresh_tokens(old_refresh)

        # Try to reuse the old token — should fail
        with pytest.raises(TokenInvalidError):
            await service.refresh_tokens(old_refresh)
