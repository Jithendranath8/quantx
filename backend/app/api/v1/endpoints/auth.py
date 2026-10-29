"""
QuantX — Authentication API Endpoints.

Thin route handlers that delegate to AuthService.
Handles HTTP concerns (request parsing, status codes) only.
"""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_async_session
from app.core.dependencies import CurrentUserId, RateLimiter, get_client_ip
from app.core.exceptions import NotFoundError, OAuthSignInError, QuantXError
from app.core.logging import get_logger
from app.core.redis import get_redis_client
from app.schemas.auth import (
    AuthResponse,
    MessageResponse,
    OAuthExchangeRequest,
    OAuthLinkStartRequest,
    OAuthLinkStartResponse,
    OAuthProviderInfo,
    TokenRefreshRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import AuthService
from app.services.oauth_service import OAuthService, enabled_providers

logger = get_logger(__name__)
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


# ── OAuth 2.0 ────────────────────────────────────────────────────────


_oauth_limit = Depends(RateLimiter("auth_oauth", _settings.rate_limit_login_per_minute))


def _frontend_redirect(fragment: str) -> RedirectResponse:
    """Send the browser back to the SPA, carrying data only in the URL fragment.

    Fragments are never sent to a server, so the one-time code stays out of
    access logs and Referer headers.
    """
    base = get_settings().frontend_url.rstrip("/")
    return RedirectResponse(f"{base}/auth/callback#{fragment}", status_code=302)


@router.get(
    "/oauth/providers",
    response_model=list[OAuthProviderInfo],
    summary="List configured OAuth providers",
)
async def oauth_providers() -> list[OAuthProviderInfo]:
    """Providers with credentials configured; the login page shows only these."""
    return [OAuthProviderInfo(name=p.name, label=p.label) for p in enabled_providers()]


@router.get(
    "/oauth/{provider}/authorize",
    summary="Start an OAuth 2.0 sign-in",
    description="Redirects to the provider's consent screen (Authorization Code flow with PKCE).",
    dependencies=[_oauth_limit],
)
async def oauth_authorize(
    provider: str,
    redis: Annotated[Redis, Depends(get_redis_client)],  # type: ignore[type-arg]
    client_nonce: Annotated[str, Query(min_length=32, max_length=128)],
) -> RedirectResponse:
    """Redirect the browser to the provider.

    ``client_nonce`` is a random value the SPA keeps in sessionStorage; only a
    browser holding it can redeem the resulting login code.
    """
    url = await OAuthService(redis).start(provider, client_nonce)
    return RedirectResponse(url, status_code=302)


@router.get(
    "/oauth/{provider}/callback",
    summary="OAuth 2.0 provider callback",
    include_in_schema=False,
)
async def oauth_callback(
    provider: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    redis: Annotated[Redis, Depends(get_redis_client)],  # type: ignore[type-arg]
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Finish the provider dance and hand the SPA a one-time login code.

    This endpoint is reached by a browser navigation, so failures redirect to
    the login page with a readable reason instead of returning JSON.
    """
    if error or not code or not state:
        return _frontend_redirect("error=cancelled" if error == "access_denied" else "error=incomplete")
    oauth = OAuthService(redis)
    linking = False
    try:
        identity, stored = await oauth.identify(provider, code, state)
        if stored.get("link_user_id"):
            linking = True
            link_code = await oauth.issue_link_code(
                str(stored["link_user_id"]), provider, identity.email, str(stored["nonce"])
            )
            return _frontend_redirect(f"link_code={quote(link_code)}")
        user = await AuthService(db).resolve_oauth_user(
            identity.email, identity.full_name, provider, ip_address=_get_client_ip(request)
        )
        login_code = await oauth.issue_login_code(str(user.id), str(stored["nonce"]))
    except OAuthSignInError as exc:
        return _frontend_redirect(f"{'link_error' if linking else 'error'}={quote(exc.code)}")
    except NotFoundError:
        return _frontend_redirect("error=provider_unavailable")
    except QuantXError as exc:
        logger.warning("oauth_callback_failed", provider=provider, error=exc.message)
        return _frontend_redirect("error=unknown")
    return _frontend_redirect(f"code={quote(login_code)}")


@router.post(
    "/oauth/{provider}/link",
    response_model=OAuthLinkStartResponse,
    summary="Start linking an OAuth provider to the signed-in account",
    dependencies=[_oauth_limit],
)
async def oauth_link_start(
    provider: str,
    data: OAuthLinkStartRequest,
    user_id: CurrentUserId,
    redis: Annotated[Redis, Depends(get_redis_client)],  # type: ignore[type-arg]
) -> OAuthLinkStartResponse:
    """Return the consent URL for linking; the browser navigates there itself.

    A navigation cannot carry the bearer token, so the authenticated part
    happens here and is recorded in the single-use state.
    """
    url = await OAuthService(redis).start(provider, data.client_nonce, link_user_id=str(user_id))
    return OAuthLinkStartResponse(authorize_url=url)


@router.post(
    "/oauth/link/complete",
    response_model=UserResponse,
    summary="Finish linking an OAuth provider to the signed-in account",
    dependencies=[_oauth_limit],
)
async def oauth_link_complete(
    data: OAuthExchangeRequest,
    request: Request,
    user_id: CurrentUserId,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    redis: Annotated[Redis, Depends(get_redis_client)],  # type: ignore[type-arg]
) -> UserResponse:
    """Attach the provider once the same user, in the same browser, confirms."""
    provider, email = await OAuthService(redis).redeem_link_code(data.code, data.client_nonce, str(user_id))
    user = await AuthService(db).link_oauth(str(user_id), email, provider, ip_address=_get_client_ip(request))
    return UserResponse.model_validate(user)


@router.post(
    "/oauth/exchange",
    response_model=AuthResponse,
    summary="Trade a one-time OAuth login code for tokens",
    dependencies=[_oauth_limit],
)
async def oauth_exchange(
    data: OAuthExchangeRequest,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    redis: Annotated[Redis, Depends(get_redis_client)],  # type: ignore[type-arg]
) -> AuthResponse:
    """Redeem the code from the callback redirect for the usual JWT pair."""
    user_id = await OAuthService(redis).redeem_login_code(data.code, data.client_nonce)
    return await AuthService(db).issue_for_user(user_id)
