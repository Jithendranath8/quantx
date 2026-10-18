"""
QuantX — Rate limiter fail-mode tests.

A Redis outage must not silently remove the brute-force throttle on the auth
endpoints (fail closed), while other scopes stay available (fail open).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request

from app.core.dependencies import RateLimiter
from app.core.exceptions import RateLimitError


def _request() -> Request:
    return Request({"type": "http", "client": ("1.2.3.4", 1234), "headers": []})


@pytest.mark.unit
class TestRateLimiterFailMode:
    @pytest.mark.asyncio
    async def test_auth_scope_fails_closed_on_redis_error(self) -> None:
        with (
            patch(
                "app.core.dependencies.get_settings",
                return_value=SimpleNamespace(rate_limit_enabled=True),
            ),
            patch(
                "app.core.dependencies.get_redis_client",
                new=AsyncMock(side_effect=RuntimeError("redis down")),
            ),
            pytest.raises(RateLimitError),
        ):
            await RateLimiter("auth_login", max_requests=5)(_request())

    @pytest.mark.asyncio
    async def test_non_auth_scope_fails_open_on_redis_error(self) -> None:
        with (
            patch(
                "app.core.dependencies.get_settings",
                return_value=SimpleNamespace(rate_limit_enabled=True),
            ),
            patch(
                "app.core.dependencies.get_redis_client",
                new=AsyncMock(side_effect=RuntimeError("redis down")),
            ),
        ):
            # Must NOT raise — a cache blip cannot take the API down.
            await RateLimiter("backtest_run", max_requests=5)(_request())
