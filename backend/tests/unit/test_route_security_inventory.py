"""
QuantX — Route security inventory.

These tests look at the application's route table, not at one route. They fail
when a new endpoint is added without the protections every endpoint is
expected to have, which is how most of the 2026-11-12 audit findings arose:
a route added later that skipped a check its neighbours had.

If a test here fails for a route you just added, either add the missing
dependency or, when the route is meant to be public, add it to the explicit
list below so the decision is visible in review.
"""

from collections.abc import Iterator
from typing import Any

from fastapi.routing import APIRoute, APIWebSocketRoute

from app.core.dependencies import RateLimiter, get_current_user, require_live_trader
from app.main import app

# Routes that are reachable without a signed-in user, each for a stated reason.
PUBLIC_ROUTES: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/auth/register"): "sign-up",
    ("POST", "/api/v1/auth/login"): "sign-in",
    ("POST", "/api/v1/auth/refresh"): "authenticated by the refresh token",
    ("POST", "/api/v1/auth/logout"): "authenticated by the refresh token",
    ("GET", "/api/v1/auth/oauth/providers"): "login page needs the provider list",
    ("GET", "/api/v1/auth/oauth/{provider}/authorize"): "starts provider sign-in",
    ("GET", "/api/v1/auth/oauth/{provider}/callback"): "provider redirect, bound by state and PKCE",
    ("POST", "/api/v1/auth/oauth/exchange"): "authenticated by a one-time code and browser nonce",
    ("GET", "/api/v1/indicators/timeframes"): "static list",
    ("POST", "/api/v1/internal/jobs/{job_name}"): "authenticated by the cron secret",
    ("GET", "/health"): "liveness probe",
    ("GET", "/ready"): "readiness probe",
    ("GET", "/metrics"): "authenticated by the metrics password",
}

# Listed above but only registered when the feature is switched on, so their
# absence is not a stale entry.
OPTIONAL_ROUTES = {("GET", "/metrics")}  # PROMETHEUS_ENABLED

# Routes that send signed requests to the exchange to open risk.
LIVE_ORDER_ROUTES = {("POST", "/api/v1/live/orders")}


def _all_routes() -> Iterator[tuple[str, Any, Any]]:
    """Yield (full path, route, effective dependant) for every route.

    Newer FastAPI keeps an included router as one nested entry and applies its
    prefix and router-level dependencies lazily, so the route table has to be
    walked through those entries; older versions list every route flat.
    """
    for route in app.routes:
        if isinstance(route, APIRoute | APIWebSocketRoute):
            yield route.path, route, route.dependant
            continue
        contexts = getattr(route, "effective_route_contexts", None)
        if contexts is None:
            continue
        for context in contexts() if callable(contexts) else contexts:
            original = context.original_route
            path = getattr(context, "path", None) or original.path
            yield path, original, getattr(context, "dependant", None) or original.dependant


def _api_routes() -> Iterator[tuple[str, str, Any]]:
    for path, route, dependant in _all_routes():
        if isinstance(route, APIRoute):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                yield method, path, dependant


def _dependency_calls(dependant: Any) -> Iterator[Any]:
    for dep in dependant.dependencies:
        yield dep.call
        yield from _dependency_calls(dep)


def _calls(dependant: Any) -> list[Any]:
    return list(_dependency_calls(dependant))


def test_the_inventory_sees_the_whole_application() -> None:
    """Guard the guard: if the walker stops finding routes, these tests prove nothing."""
    assert len(list(_api_routes())) > 60


def test_every_route_requires_a_signed_in_user_unless_listed_public() -> None:
    unprotected = [
        f"{method} {path}"
        for method, path, route in _api_routes()
        if (method, path) not in PUBLIC_ROUTES and get_current_user not in _calls(route)
    ]
    assert unprotected == [], f"Routes with no authentication: {unprotected}"


def test_the_public_list_has_no_stale_entries() -> None:
    existing = {(method, path) for method, path, _ in _api_routes()}
    assert set(PUBLIC_ROUTES) - existing - OPTIONAL_ROUTES == set()


def test_public_routes_stay_public_on_purpose() -> None:
    """A route on the public list must not quietly gain or need user auth."""
    for method, path, route in _api_routes():
        if (method, path) in PUBLIC_ROUTES:
            assert get_current_user not in _calls(route), f"{method} {path} is listed public but requires a user"


def test_placing_live_orders_requires_the_live_trading_permission() -> None:
    for method, path, route in _api_routes():
        if (method, path) in LIVE_ORDER_ROUTES:
            assert require_live_trader in _calls(route), f"{method} {path} must require the live-trading permission"
    assert {(m, p) for m, p, _ in _api_routes()} >= LIVE_ORDER_ROUTES


def test_every_api_route_is_rate_limited() -> None:
    unlimited = [
        f"{method} {path}"
        for method, path, route in _api_routes()
        if path.startswith("/api/") and not any(isinstance(call, RateLimiter) for call in _calls(route))
    ]
    assert unlimited == [], f"Routes with no rate limit: {unlimited}"


def test_unauthenticated_state_changing_routes_have_their_own_limit() -> None:
    """Public POST routes need a specific limit, not just the global backstop."""
    for method, path, route in _api_routes():
        if (method, path) in PUBLIC_ROUTES and method == "POST" and path.startswith("/api/v1/auth/"):
            scopes = {call.scope for call in _calls(route) if isinstance(call, RateLimiter)}
            assert scopes - {"api_global"}, f"{method} {path} has no dedicated rate limit"


def test_websocket_routes_are_known() -> None:
    """A new WebSocket route must be reviewed: they bypass HTTP dependencies."""
    paths = {path for path, route, _ in _all_routes() if isinstance(route, APIWebSocketRoute)}
    assert paths == {"/ws/market/{symbol}", "/ws/health"}
