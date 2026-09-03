"""
QuantX — Authentication API Endpoints.

Thin route handlers that delegate to AuthService.
Handles HTTP concerns (request parsing, status codes) only.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_async_session
from app.core.dependencies import CurrentUserId, RateLimiter, get_client_ip
from app.schemas.auth import (
    AuthResponse,
    MessageResponse,
    TokenRefreshRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _get_client_ip(request: Request) -> str | None:
    """Client IP for audit logging.

    X-Forwarded-For is not consulted: it is set by the client and trusting it
    lets an attacker forge every audit-log entry and evade IP rate limits.
    Run behind a proxy with --proxy-headers and a trusted-host list instead.
    """
    return get_client_ip(request)


_settings = get_settings()

# Login and registration are unauthenticated and each does bcrypt work, so
# they are the cheapest way to burn a worker's CPU. Both are throttled per IP.
_login_limit = Depends(RateLimiter("auth_login", _settings.rate_limit_login_per_minute))
_register_limit = Depends(RateLimiter("auth_register", _settings.rate_limit_login_per_minute))
_refresh_limit = Depends(RateLimiter("auth_refresh", _settings.rate_limit_default_per_minute))


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=201,
    summary="Register a new user account",
    description="Create a new user with email, username, and password. Returns user data and auth tokens.",
    dependencies=[_register_limit],
)
async def register(
    data: UserRegisterRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> AuthResponse:
    """Register a new user and return authentication tokens."""
    service = AuthService(db)
    return await service.register(data, ip_address=_get_client_ip(request))


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Authenticate with email and password",
    description="Login with email and password. Returns user data and auth tokens.",
    dependencies=[_login_limit],
)
async def login(
    data: UserLoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> AuthResponse:
    """Authenticate a user and return tokens."""
    service = AuthService(db)
    return await service.login(
        email=data.email,
        password=data.password,
        ip_address=_get_client_ip(request),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    description="Exchange a valid refresh token for new access and refresh tokens (token rotation).",
    dependencies=[_refresh_limit],
)
async def refresh_token(
    data: TokenRefreshRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> TokenResponse:
    """Refresh access token using a refresh token."""
    service = AuthService(db)
    return await service.refresh_tokens(
        refresh_token=data.refresh_token,
        ip_address=_get_client_ip(request),
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout current session",
    description="Revoke the provided refresh token, ending the current session.",
)
async def logout(
    data: TokenRefreshRequest,
    request: Request,
    user_id: CurrentUserId,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """Logout by revoking the refresh token."""
    service = AuthService(db)
    return await service.logout(
        refresh_token=data.refresh_token,
        user_id=user_id,
        ip_address=_get_client_ip(request),
    )


@router.post(
    "/logout-all",
    response_model=MessageResponse,
    summary="Logout from all devices",
    description="Revoke all refresh tokens for the current user, ending all sessions.",
)
async def logout_all(
    request: Request,
    user_id: CurrentUserId,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """Logout from all devices by revoking all refresh tokens."""
    service = AuthService(db)
    return await service.logout_all(
        user_id=user_id,
        ip_address=_get_client_ip(request),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
    description="Returns the profile of the currently authenticated user.",
)
async def get_me(
    user_id: CurrentUserId,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> UserResponse:
    """Get the current authenticated user's profile."""
    service = AuthService(db)
    return await service.get_user(user_id)
