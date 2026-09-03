"""
QuantX — Unit Tests for Security Module.

Tests JWT token creation, validation, expiration, and password hashing.
These tests run without database connectivity.
"""

from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from app.core.config import get_settings
from app.core.exceptions import TokenExpiredError, TokenInvalidError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_access_token,
    verify_password,
    verify_refresh_token,
)

settings = get_settings()


class TestPasswordHashing:
    """Tests for password hashing and verification."""

    def test_hash_password_returns_bcrypt_hash(self) -> None:
        """Hashed password should start with bcrypt prefix."""
        hashed = hash_password("MySecureP@ss1")
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60

    def test_verify_correct_password(self) -> None:
        """Correct password should verify successfully."""
        password = "TestP@ssword123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self) -> None:
        """Wrong password should fail verification."""
        hashed = hash_password("CorrectPassword1")
        assert verify_password("WrongPassword1", hashed) is False

    def test_different_hashes_for_same_password(self) -> None:
        """Hashing the same password twice should produce different hashes (due to salt)."""
        h1 = hash_password("SamePassword1")
        h2 = hash_password("SamePassword1")
        assert h1 != h2
        # But both should verify
        assert verify_password("SamePassword1", h1)
        assert verify_password("SamePassword1", h2)


class TestAccessToken:
    """Tests for JWT access token creation and verification."""

    def test_create_access_token(self) -> None:
        """Access token should be a valid JWT with correct claims."""
        token = create_access_token(subject="user-123")
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])

        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"
        assert "exp" in payload
        assert "iat" in payload

    def test_create_access_token_with_extra_claims(self) -> None:
        """Extra claims should be included in the token."""
        token = create_access_token(
            subject="user-456",
            extra_claims={"email": "test@example.com", "role": "trader"},
        )
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])

        assert payload["email"] == "test@example.com"
        assert payload["role"] == "trader"

    def test_verify_valid_access_token(self) -> None:
        """Valid access token should return the subject."""
        token = create_access_token(subject="user-789")
        subject = verify_access_token(token)
        assert subject == "user-789"

    def test_verify_expired_access_token(self) -> None:
        """Expired access token should raise TokenExpiredError."""
        # Create a token that expired 1 hour ago
        expire = datetime.now(UTC) - timedelta(hours=1)
        payload = {
            "sub": "user-expired",
            "exp": expire,
            "iat": datetime.now(UTC),
            "type": "access",
        }
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

        with pytest.raises(TokenExpiredError):
            verify_access_token(token)

    def test_verify_invalid_token_string(self) -> None:
        """Malformed token should raise TokenInvalidError."""
        with pytest.raises(TokenInvalidError):
            verify_access_token("not.a.valid.jwt")

    def test_verify_wrong_secret(self) -> None:
        """Token signed with wrong secret should raise TokenInvalidError."""
        payload = {
            "sub": "user-wrong-key",
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(payload, "wrong-secret-key", algorithm="HS256")

        with pytest.raises(TokenInvalidError):
            verify_access_token(token)

    def test_verify_refresh_token_as_access_rejects(self) -> None:
        """Refresh token should not be accepted as access token."""
        token = create_refresh_token(subject="user-123")
        with pytest.raises(TokenInvalidError, match="Not an access token"):
            verify_access_token(token)


class TestRefreshToken:
    """Tests for JWT refresh token creation and verification."""

    def test_create_refresh_token(self) -> None:
        """Refresh token should have type=refresh and longer expiry."""
        token = create_refresh_token(subject="user-123")
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])

        assert payload["sub"] == "user-123"
        assert payload["type"] == "refresh"

    def test_verify_valid_refresh_token(self) -> None:
        """Valid refresh token should return the subject."""
        token = create_refresh_token(subject="user-abc")
        subject = verify_refresh_token(token)
        assert subject == "user-abc"

    def test_verify_access_token_as_refresh_rejects(self) -> None:
        """Access token should not be accepted as refresh token."""
        token = create_access_token(subject="user-123")
        with pytest.raises(TokenInvalidError, match="Not a refresh token"):
            verify_refresh_token(token)

    def test_token_without_subject_rejects(self) -> None:
        """Token without sub claim should raise TokenInvalidError."""
        payload = {
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

        with pytest.raises(TokenInvalidError, match="Token missing subject"):
            verify_access_token(token)
