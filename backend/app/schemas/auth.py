"""
QuantX — Authentication & User Schemas.

Pydantic models for request validation and response serialization
across all authentication endpoints.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ── Request Schemas ──────────────────────────────────────────────────


class UserRegisterRequest(BaseModel):
    """Schema for user registration."""

    email: EmailStr = Field(..., description="User email address", examples=["trader@quantx.io"])
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Username (alphanumeric, hyphens, underscores)",
        examples=["crypto_trader"],
    )
    password: str = Field(
        ...,
        min_length=8,
        # 72 bytes is bcrypt's hard limit; anything longer would be silently
        # truncated, making two different passwords interchangeable.
        max_length=72,
        description="Password (8-72 characters)",
        examples=["StrongP@ss123"],
    )
    full_name: str | None = Field(
        None,
        max_length=100,
        description="Full name (optional)",
        examples=["John Doe"],
    )


class UserLoginRequest(BaseModel):
    """Schema for user login (email + password)."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class TokenRefreshRequest(BaseModel):
    """Schema for refreshing an access token."""

    refresh_token: str = Field(..., description="Valid refresh token")


class PasswordChangeRequest(BaseModel):
    """Schema for changing password."""

    current_password: str = Field(..., description="Current password")
    new_password: str = Field(
        ...,
        min_length=8,
        # 72 bytes is bcrypt's hard limit; anything longer would be silently
        # truncated, making two different passwords interchangeable.
        max_length=72,
        description="New password (8-72 characters)",
    )


class UserUpdateRequest(BaseModel):
    """Schema for updating user profile."""

    full_name: str | None = Field(None, max_length=100)
    bio: str | None = Field(None, max_length=500)


# ── Response Schemas ─────────────────────────────────────────────────


class UserResponse(BaseModel):
    """Schema for user data in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    username: str
    full_name: str | None = None
    is_active: bool
    is_superuser: bool
    bio: str | None = None
    # Provider that can sign this account in, or None for password-only.
    oauth_provider: str | None = None
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    """Schema for authentication token response."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiry in seconds")


class AuthResponse(BaseModel):
    """Schema combining user data with tokens (used after login/register)."""

    user: UserResponse
    tokens: TokenResponse


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str
    success: bool = True


class OAuthProviderInfo(BaseModel):
    """A sign-in provider the login page can offer."""

    name: str
    label: str


class OAuthExchangeRequest(BaseModel):
    """The one-time code handed to the SPA after a provider sign-in."""

    code: str = Field(..., min_length=16, max_length=128)
    # The random value the SPA generated when it started this sign-in.
    client_nonce: str = Field(..., min_length=32, max_length=128)


class OAuthLinkStartRequest(BaseModel):
    """Nonce of the browser starting a provider link."""

    client_nonce: str = Field(..., min_length=32, max_length=128)


class OAuthLinkStartResponse(BaseModel):
    """Where to send the browser to link a provider to the signed-in account."""

    authorize_url: str
