"""
QuantX — FastAPI Dependencies.

Provides reusable dependencies for authentication, database sessions,
Redis clients, rate limiting, and pagination that are injected via Depends().
"""

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_async_session
from app.core.exceptions import AuthenticationError, AuthorizationError, RateLimitError
from app.core.logging import get_logger
from app.core.redis import RedisManager, get_redis_client
from app.core.security import verify_access_claims
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


async def get_access_claims(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> dict[str, Any]:
    """Verify the bearer token's signature, type and expiry.

    Raises:
        AuthenticationError: If the token is invalid or expired.
    """
    try:
        return verify_access_claims(token)
    except Exception as e:
        raise AuthenticationError(str(e)) from e


async def authenticate_claims(claims: dict[str, Any], db: AsyncSession) -> User:
    """Turn verified access-token claims into a live, authorised user.

    A valid signature is not enough. The account must still exist and be
    active, and the sign-in the token belongs to must not have been ended:
    logout, "sign out everywhere" and refresh-token reuse detection all revoke
    the session's refresh tokens, and the access token is refused from that
    moment instead of lingering until it expires.

    Raises:
        AuthenticationError: If the user is gone or the session was ended.
        AuthorizationError: If the user is deactivated.
    """
    # Imported here to avoid a circular import at module load.
    from app.repositories.user_repository import RefreshTokenRepository, UserRepository

    user = await UserRepository(db).get_by_id(str(claims["sub"]))
    if user is None:
        raise AuthenticationError("User not found")
    if not user.is_active:
        raise AuthorizationError("User account is deactivated")

    session_id = claims.get("sid")
    if session_id is not None:
        try:
            family_id = uuid.UUID(str(session_id))
        except ValueError as exc:
            raise AuthenticationError("Invalid session") from exc
        if not await RefreshTokenRepository(db).family_alive(family_id):
            raise AuthenticationError("Session has ended. Please sign in again.")
    # Tokens issued before sessions were tracked carry no ``sid``. They are at
    # most one access-token lifetime old and simply age out.
    return user


async def get_current_user(
    claims: Annotated[dict[str, Any], Depends(get_access_claims)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> User:
    """Load the authenticated User record for a live session.

    Returns the ORM model (not a dict) so routes and services can rely on
    typed attributes such as ``user.id`` and ``user.is_superuser``.

    Raises:
        AuthenticationError: If the user is not found or the session ended.
        AuthorizationError: If the user is deactivated.
    """
    return await authenticate_claims(claims, db)


async def get_current_user_id(
    user: Annotated[User, Depends(get_current_user)],
) -> str:
    """The authenticated user's id.

    Resolved through ``get_current_user`` on purpose: a route that needs only
    the id must still reject a deactivated account or an ended session.
    """
    return str(user.id)


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


async def require_live_trader(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Ensure the current user may place orders on the operator's exchange account.

    Raises:
        AuthorizationError: If live trading has not been granted to this account.
    """
    if not current_user.can_trade_live:
        raise AuthorizationError(
            "Live trading is not enabled for this account. Ask the operator to grant it."
        )
    return current_user


class _LocalWindowCounter:
    """In-process fixed-window counter, used when Redis cannot be reached.

    Per worker and approximate, but it means a Redis outage degrades rate
    limiting instead of switching it off. Failing fully open made an outage (or
    anything that exhausted the Redis pool) remove the brute-force limit on
    login and the throttle on live orders at the same moment.
    """

    MAX_KEYS = 50_000

    def __init__(self) -> None:
        self._windows: dict[str, tuple[float, int]] = {}

    def hit(self, key: str, window_seconds: int) -> int:
        """Count one request against ``key`` and return the window's total."""
        now = time.monotonic()
        started, count = self._windows.get(key, (now, 0))
        if now - started >= window_seconds:
            started, count = now, 0
        count += 1
        if len(self._windows) >= self.MAX_KEYS and key not in self._windows:
            self._prune(now, window_seconds)
        self._windows[key] = (started, count)
        return count

    def _prune(self, now: float, window_seconds: int) -> None:
        expired = [k for k, (started, _) in self._windows.items() if now - started >= window_seconds]
        for k in expired:
            del self._windows[k]
        if len(self._windows) >= self.MAX_KEYS:
            # Still full of live windows: drop the oldest half rather than grow.
            for k in sorted(self._windows, key=lambda k: self._windows[k][0])[: self.MAX_KEYS // 2]:
                del self._windows[k]


_local_counter = _LocalWindowCounter()


def rate_limit_identity(request: Request) -> str:
    """Who a request is counted against.

    A request carrying a valid access token is counted per user. Otherwise it
    is counted per client address. Counting everything per address meant that
    behind a reverse proxy, where every client can appear to come from the
    proxy's address, all users shared one bucket and one caller could exhaust
    it for everybody.
    """
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            return f"user:{verify_access_claims(token.strip())['sub']}"
        except Exception:
            pass  # not a valid token: fall through to the address
    return f"ip:{get_client_ip(request)}"


class RateLimiter:
    """Fixed-window rate limiter usable as a route dependency.

    Usage:
        @router.post("/expensive", dependencies=[Depends(RateLimiter("backtest", 5))])

    Requests are counted per authenticated user, or per client address when
    there is no valid token (see :func:`rate_limit_identity`). The count lives
    in Redis; if Redis cannot be reached the limiter falls back to an
    in-process counter, so an outage never blocks a real user and never
    removes the limit either.
    """

    def __init__(self, scope: str, max_requests: int, window_seconds: int = 60) -> None:
        self.scope = scope
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def __call__(self, request: Request) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return

        identifier = rate_limit_identity(request)
        key = f"ratelimit:{self.scope}:{identifier}"
        try:
            manager = RedisManager(await get_redis_client())
            limited = await manager.is_rate_limited(
                key, self.max_requests, self.window_seconds
            )
        except Exception as exc:
            logger.warning("rate_limit_redis_unavailable", scope=self.scope, error=str(exc))
            limited = _local_counter.hit(key, self.window_seconds) > self.max_requests

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


class ConcurrencyLimit:
    """Caps how many requests of one kind a single user can have in flight.

    A per-minute rate limit does not bound work that lasts longer than a
    minute. Agent runs wait on a model for a long time, so a handful of
    in-limit requests could hold a worker's resources indefinitely.

    Usage:
        async with agent_runs.slot(str(user.id)):
            ...
    """

    def __init__(self, scope: str, max_concurrent: int) -> None:
        self.scope = scope
        self.max_concurrent = max_concurrent
        self._in_flight: dict[str, int] = {}

    @asynccontextmanager
    async def slot(self, identity: str) -> AsyncIterator[None]:
        """Hold one slot for ``identity``; refuse when they are all taken."""
        current = self._in_flight.get(identity, 0)
        if current >= self.max_concurrent:
            raise RateLimitError(
                f"Too many concurrent {self.scope} requests. "
                f"Wait for one of your {self.max_concurrent} running requests to finish.",
                retry_after_seconds=10,
            )
        self._in_flight[identity] = current + 1
        try:
            yield
        finally:
            remaining = self._in_flight.get(identity, 1) - 1
            if remaining <= 0:
                self._in_flight.pop(identity, None)
            else:
                self._in_flight[identity] = remaining


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
