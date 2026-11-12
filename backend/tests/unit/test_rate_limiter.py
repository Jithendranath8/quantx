"""
QuantX — Rate limiter tests.

Two properties are pinned here.

A Redis problem (outage, or an exhausted free-tier command quota) must never
lock users out or take the API down: requests keep flowing. But it must not
switch the limit off either, which is what "fail open" used to mean; the
limiter falls back to counting in-process.

Requests are counted per authenticated user. Counting everything per client
address meant that behind a reverse proxy, where every client can appear to
come from the proxy's address, all users shared one bucket.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request

from app.core.dependencies import ConcurrencyLimit, RateLimiter, rate_limit_identity
from app.core.exceptions import RateLimitError
from app.core.security import create_access_token

PROXY = "172.18.0.9"


def _request(token: str | None = None, ip: str = "1.2.3.4") -> Request:
    headers = [(b"authorization", f"Bearer {token}".encode())] if token else []
    return Request({"type": "http", "client": (ip, 1234), "headers": headers})


def _redis_down() -> object:
    return patch(
        "app.core.dependencies.get_redis_client",
        new=AsyncMock(side_effect=RuntimeError("max requests limit exceeded")),
    )


def _limits_on() -> object:
    return patch("app.core.dependencies.get_settings", return_value=SimpleNamespace(rate_limit_enabled=True))


@pytest.mark.unit
class TestRateLimiterFailMode:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("scope", ["auth_login", "auth_register", "backtest_run"])
    async def test_a_redis_error_never_blocks_a_request_within_its_limit(self, scope: str) -> None:
        with _limits_on(), _redis_down():
            await RateLimiter(f"{scope}-{uuid.uuid4().hex}", max_requests=5)(_request())  # must not raise

    @pytest.mark.asyncio
    async def test_a_redis_error_does_not_switch_the_limit_off(self) -> None:
        """With Redis down the limit still applies, counted in-process."""
        limiter = RateLimiter(f"login-{uuid.uuid4().hex}", max_requests=3)
        with _limits_on(), _redis_down():
            for _ in range(3):
                await limiter(_request())
            with pytest.raises(RateLimitError):
                await limiter(_request())


@pytest.mark.unit
class TestRateLimitIdentity:
    def test_an_authenticated_request_is_counted_per_user(self) -> None:
        user_id = str(uuid.uuid4())
        assert rate_limit_identity(_request(create_access_token(subject=user_id), ip=PROXY)) == f"user:{user_id}"

    @pytest.mark.parametrize("token", [None, "not-a-jwt"])
    def test_everything_else_is_counted_per_address(self, token: str | None) -> None:
        assert rate_limit_identity(_request(token, ip=PROXY)) == f"ip:{PROXY}"

    @pytest.mark.asyncio
    async def test_users_behind_one_proxy_do_not_share_a_bucket(self) -> None:
        """Security audit finding 6: one caller must not exhaust everyone's limit."""
        limiter = RateLimiter(f"orders-{uuid.uuid4().hex}", max_requests=2)
        noisy = create_access_token(subject=str(uuid.uuid4()))
        quiet = create_access_token(subject=str(uuid.uuid4()))
        with _limits_on(), _redis_down():
            for _ in range(2):
                await limiter(_request(noisy, ip=PROXY))
            with pytest.raises(RateLimitError):
                await limiter(_request(noisy, ip=PROXY))
            await limiter(_request(quiet, ip=PROXY))  # same address, own bucket


@pytest.mark.unit
class TestConcurrencyLimit:
    @pytest.mark.asyncio
    async def test_a_user_cannot_hold_more_than_their_share(self) -> None:
        limit = ConcurrencyLimit("agent", max_concurrent=2)
        async with limit.slot("alice"), limit.slot("alice"):
            with pytest.raises(RateLimitError):
                async with limit.slot("alice"):
                    pass
            async with limit.slot("bob"):  # another user is unaffected
                pass
        async with limit.slot("alice"):  # released on exit
            pass

    @pytest.mark.asyncio
    async def test_a_slot_is_released_when_the_work_fails(self) -> None:
        limit = ConcurrencyLimit("agent", max_concurrent=1)
        with pytest.raises(ValueError):
            async with limit.slot("alice"):
                raise ValueError("boom")
        async with limit.slot("alice"):
            pass
