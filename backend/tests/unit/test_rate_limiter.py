"""
QuantX — Rate limiter fail-mode tests.

Rate limiting is best-effort: when Redis is unavailable (outage, or an
exhausted free-tier command quota) every scope — including auth — must fail
OPEN so a cache problem can never lock users out of login or take the API down.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request

from app.core.dependencies import RateLimiter


def _request() -> Request:
    return Request({"type": "http", "client": ("1.2.3.4", 1234), "headers": []})


@pytest.mark.unit
class TestRateLimiterFailMode:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("scope", ["auth_login", "auth_register", "backtest_run"])
    async def test_every_scope_fails_open_on_redis_error(self, scope: str) -> None:
        # A Redis failure (here an exhausted quota) must never raise — the
        # request proceeds, including for the auth endpoints.
        with (
            patch(
                "app.core.dependencies.get_settings",
                return_value=SimpleNamespace(rate_limit_enabled=True),
            ),
            patch(
                "app.core.dependencies.get_redis_client",
                new=AsyncMock(side_effect=RuntimeError("max requests limit exceeded")),
            ),
        ):
            await RateLimiter(scope, max_requests=5)(_request())  # must not raise
