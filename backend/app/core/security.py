"""
QuantX — Security Utilities.

JWT token creation/validation and password hashing.

Password hashing uses the ``bcrypt`` library directly rather than passlib.
passlib 1.7.4 (its last release, from 2020) reads ``bcrypt.__about__`` to
detect the backend version; that attribute was removed in bcrypt 4.1, so the
combination pinned by this project -- ``passlib>=1.7.4`` with ``bcrypt>=4.2``
-- fails at import with "error reading bcrypt version" and then raises on the
first hash. Calling bcrypt directly removes an unmaintained dependency from the
authentication path. The stored hash format is unchanged ($2b$), so hashes
written by the previous passlib configuration still verify.
"""

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.exceptions import TokenExpiredError, TokenInvalidError, ValidationError

settings = get_settings()

# ── Password Hashing ─────────────────────────────────────────────────

BCRYPT_ROUNDS = 12

# bcrypt hashes at most 72 bytes and silently ignores everything beyond that,
# which would make "correct-horse-battery-staple…" and a different 100-byte
# password with the same first 72 bytes interchangeable. Long passwords are
# rejected explicitly instead of being truncated behind the user's back.
MAX_PASSWORD_BYTES = 72


def _encode(password: str) -> bytes:
    """UTF-8 encode a password, rejecting anything bcrypt would truncate.

    Raises:
        ValidationError: If the password exceeds bcrypt's 72-byte limit.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValidationError(
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded "
            f"(received {len(encoded)})."
        )
    return encoded


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt.

    Args:
        plain_password: The plaintext password to hash.

    Returns:
        The bcrypt hash string.

    Raises:
        ValidationError: If the password is longer than 72 bytes.
    """
    return bcrypt.hashpw(_encode(plain_password), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode(
        "utf-8"
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Args:
        plain_password: The plaintext password to verify.
        hashed_password: The stored bcrypt hash.

    Returns:
        True if the password matches, False otherwise. Never raises on a
        malformed stored hash: that is a failed verification, not a crash in
        the login path.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8")[:MAX_PASSWORD_BYTES],
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


# ── JWT Token Management ─────────────────────────────────────────────


def create_access_token(subject: str, extra_claims: dict | None = None) -> str:
    """Create a JWT access token.

    Args:
        subject: The token subject (typically user ID as string).
        extra_claims: Optional additional claims to include.

    Returns:
        Encoded JWT string.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
        "iat": now,
        "jti": uuid.uuid4().hex,
        "type": "access",
    }
    if extra_claims:
        # Reserved claims are set last so a caller cannot override the subject,
        # expiry or token type through extra_claims.
        payload = {**extra_claims, **payload}

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str) -> str:
    """Create a JWT refresh token with longer expiry.

    Args:
        subject: The token subject (typically user ID as string).

    Returns:
        Encoded JWT string.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "exp": now + timedelta(days=settings.jwt_refresh_token_expire_days),
        "iat": now,
        # A unique token id per issuance. Without it two refresh tokens minted
        # for the same user inside the same second have byte-identical payloads,
        # so they encode to the same JWT and collide on the unique index over
        # token_hash -- turning a fast re-login or a token rotation into a 500.
        "jti": uuid.uuid4().hex,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token.

    Args:
        token: The JWT string to decode.

    Returns:
        The decoded token payload.

    Raises:
        TokenExpiredError: If the token has expired.
        TokenInvalidError: If the token is malformed or invalid.
    """
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as e:
        error_msg = str(e).lower()
        if "expired" in error_msg:
            raise TokenExpiredError() from e
        raise TokenInvalidError() from e


# Article per token type, so messages read naturally ("Not an access token").
_TOKEN_TYPE_ARTICLE = {"access": "an", "refresh": "a"}


def _verify_typed_token(token: str, expected_type: str) -> str:
    """Decode a token and assert its type, returning the subject."""
    payload = decode_token(token)
    if payload.get("type") != expected_type:
        article = _TOKEN_TYPE_ARTICLE.get(expected_type, "a")
        raise TokenInvalidError(f"Not {article} {expected_type} token")
    subject: str | None = payload.get("sub")
    if not subject:
        raise TokenInvalidError("Token missing subject")
    return subject


def verify_access_token(token: str) -> str:
    """Verify an access token and return the subject (user ID).

    Args:
        token: The JWT access token string.

    Returns:
        The subject claim (user ID as string).

    Raises:
        TokenInvalidError: If the token is not an access token.
        TokenExpiredError: If the token has expired.
    """
    return _verify_typed_token(token, "access")


def verify_refresh_token(token: str) -> str:
    """Verify a refresh token and return the subject (user ID).

    Args:
        token: The JWT refresh token string.

    Returns:
        The subject claim (user ID as string).

    Raises:
        TokenInvalidError: If the token is not a refresh token.
        TokenExpiredError: If the token has expired.
    """
    return _verify_typed_token(token, "refresh")
