"""
QuantX — FastAPI Dependencies.

Provides reusable dependencies for authentication, database sessions,
Redis clients, rate limiting, and pagination that are injected via Depends().
"""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_async_session
from app.core.exceptions import AuthenticationError, AuthorizationError, RateLimitError
from app.core.logging import get_logger
from app.core.redis import RedisManager, get_redis_client
from app.core.security import verify_access_token
from app.models.user import User

logger = get_logger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_client_ip(request: Request) -> str:
    """Best-effort client IP for audit logging and rate limiting.

    X-Forwarded-For is attacker-controlled unless a trusted proxy overwrites
    it, so it is only consulted when the app is explicitly running behind one
    (uvicorn's --proxy-headers populates request.client from it). We therefore
    read the socket peer, which cannot be spoofed by the client.
    """
    if request.client is None:
        return "unknown"
    return request.client.host


async def get_current_user_id(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> str:
    """Extract and validate the current user ID from the JWT token.

    This is the core authentication dependency. It verifies the access
    token and returns the user's ID (UUID string).

    Raises:
        AuthenticationError: If the token is invalid or expired.
    """
    try:
        return verify_access_token(token)
    except Exception as e:
        raise AuthenticationError(str(e)) from e


async def get_current_user(
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> User:
    """Load the authenticated User record, ensuring the account is active.

    Returns the ORM model (not a dict) so routes and services can rely on
    typed attributes such as ``user.id`` and ``user.is_superuser``.

    Raises:
        AuthenticationError: If the user is not found.
        AuthorizationError: If the user is deactivated.
    """
    # Imported here to avoid a circular import at module load.
    from app.repositories.user_repository import UserRepository

    user = await UserRepository(db).get_by_id(user_id)
    if user is None:
        raise AuthenticationError("User not found")
    if not user.is_active:
        raise AuthorizationError("User account is deactivated")
    return user


# Retained for readability at call sites that want the intent spelled out.
get_current_active_user = get_current_user


async def require_superuser(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Ensure the current user has superuser privileges.

    Raises:
        AuthorizationError: If the user is not a superuser.
    """
    if not current_user.is_superuser:
        raise AuthorizationError("Superuser access required")
    return current_user


class RateLimiter:
    """Fixed-window rate limiter usable as a route dependency.

    Usage:
        @router.post("/expensive", dependencies=[Depends(RateLimiter("backtest", 5))])

    Requests are counted per client IP per scope. On a Redis failure, non-auth
    scopes fail *open* (the request proceeds) so a cache outage cannot take the
    API down, while ``auth*`` scopes fail *closed* so the brute-force throttle is
    never silently removed.
    """

    def __init__(self, scope: str, max_requests: int, window_seconds: int = 60) -> None:
        self.scope = scope
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def __call__(self, request: Request) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return

        identifier = get_client_ip(request)
        key = f"ratelimit:{self.scope}:{identifier}"
        try:
            manager = RedisManager(await get_redis_client())
            limited = await manager.is_rate_limited(
                key, self.max_requests, self.window_seconds
            )
        except Exception as exc:
            logger.warning("rate_limit_check_failed", scope=self.scope, error=str(exc))
            # Authentication throttles fail CLOSED: a Redis outage must not
            # silently open an unlimited password brute-force / bcrypt-CPU
            # window on login/register. Every other scope fails open so a cache
            # blip cannot take the whole API down.
            if self.scope.startswith("auth"):
                raise RateLimitError(
                    f"Rate limiting is temporarily unavailable for {self.scope}; "
                    "please retry shortly.",
                    retry_after_seconds=self.window_seconds,
                ) from exc
            return

        if limited:
            logger.warning("rate_limit_exceeded", scope=self.scope, client=identifier)
            raise RateLimitError(
                f"Rate limit exceeded for {self.scope}. "
                f"Maximum {self.max_requests} requests per {self.window_seconds}s.",
                retry_after_seconds=self.window_seconds,
            )


def default_rate_limiter(scope: str) -> RateLimiter:
    """Rate limiter using the configured default request budget."""
    return RateLimiter(scope, get_settings().rate_limit_default_per_minute)


def expensive_rate_limiter(scope: str) -> RateLimiter:
    """Rate limiter for CPU- or upstream-heavy endpoints."""
    return RateLimiter(scope, get_settings().rate_limit_expensive_per_minute)


class PaginationParams:
    """Pagination parameters extracted from query strings.

    Usage:
        @router.get("/items")
        async def list_items(pagination: PaginationParams = Depends()):
            ...
    """

    def __init__(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> None:
        self.page = max(1, page)
        self.page_size = min(max(1, page_size), 200)  # Cap at 200

    @property
    def offset(self) -> int:
        """Calculate SQL offset from page number."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Return the page size as SQL limit."""
        return self.page_size


# ── Type aliases for cleaner route signatures ────────────────────────

DBSession = Annotated[AsyncSession, Depends(get_async_session)]
CurrentUserId = Annotated[str, Depends(get_current_user_id)]
CurrentUser = Annotated[User, Depends(get_current_user)]
SuperUser = Annotated[User, Depends(require_superuser)]
Pagination = Annotated[PaginationParams, Depends()]
ClientIP = Annotated[str, Depends(get_client_ip)]
