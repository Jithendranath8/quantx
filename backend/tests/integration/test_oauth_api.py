"""
QuantX — Integration Tests for OAuth 2.0 sign-in.

The provider is replaced with an httpx MockTransport; state, PKCE and the
one-time login code all go through the real Redis, so replay protection is
exercised for real rather than assumed.
"""

from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.services import oauth_service


def _provider_handler(
    *,
    google_verified: bool = True,
    github_verified: bool = True,
    email: str = "oauth.trader@example.com",
) -> Any:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(("https://oauth2.googleapis.com/token", "https://github.com/login/oauth/access_token")):
            seen["token_form"] = parse_qs(request.content.decode())
            return httpx.Response(200, json={"access_token": "provider-token", "token_type": "bearer"})
        if url.startswith("https://openidconnect.googleapis.com/v1/userinfo"):
            return httpx.Response(200, json={"email": email, "email_verified": google_verified, "name": "OAuth Trader"})
        if url == "https://api.github.com/user":
            return httpx.Response(200, json={"login": "octo", "name": None})
        if url == "https://api.github.com/user/emails":
            return httpx.Response(200, json=[{"email": email, "primary": True, "verified": github_verified}])
        return httpx.Response(404)

    handler.seen = seen  # type: ignore[attr-defined]
    return handler


@pytest.fixture
def oauth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    for provider in ("google", "github"):
        monkeypatch.setattr(settings, f"oauth_{provider}_client_id", f"{provider}-client")
        monkeypatch.setattr(settings, f"oauth_{provider}_client_secret", f"{provider}-secret")
    monkeypatch.setattr(settings, "frontend_url", "https://app.example.com")
    monkeypatch.setattr(settings, "public_api_url", "https://api.example.com")


def _mock_provider(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    real = httpx.AsyncClient

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(oauth_service.httpx, "AsyncClient", factory)


NONCE = "browser-nonce-0123456789abcdef0123456789"


async def _start(client: AsyncClient, provider: str, nonce: str = NONCE) -> dict[str, list[str]]:
    response = await client.get(f"/api/v1/auth/oauth/{provider}/authorize", params={"client_nonce": nonce})
    assert response.status_code == 302
    return parse_qs(urlparse(response.headers["location"]).query)


def _fragment(response: httpx.Response) -> dict[str, str]:
    location = response.headers["location"]
    assert location.startswith("https://app.example.com/auth/callback#")
    key, _, value = location.split("#", 1)[1].partition("=")
    return {key: unquote(value)}


@pytest.mark.integration
class TestOAuthSignIn:
    @pytest.mark.asyncio
    async def test_no_credentials_means_no_providers(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/auth/oauth/providers")
        assert response.status_code == 200
        assert response.json() == []

        unconfigured = await client.get("/api/v1/auth/oauth/google/authorize", params={"client_nonce": NONCE})
        assert unconfigured.status_code == 404

    @pytest.mark.asyncio
    async def test_authorize_uses_state_and_pkce(self, client: AsyncClient, oauth_enabled: None) -> None:
        providers = (await client.get("/api/v1/auth/oauth/providers")).json()
        assert {p["name"] for p in providers} == {"google", "github"}

        params = await _start(client, "google")
        assert params["client_id"] == ["google-client"]
        assert params["redirect_uri"] == ["https://api.example.com/api/v1/auth/oauth/google/callback"]
        assert params["code_challenge_method"] == ["S256"]
        assert len(params["state"][0]) >= 32
        assert params["code_challenge"][0]

    @pytest.mark.asyncio
    async def test_full_google_flow_creates_account_and_code_is_single_use(
        self, client: AsyncClient, oauth_enabled: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        handler = _provider_handler()
        _mock_provider(monkeypatch, handler)
        state = (await _start(client, "google"))["state"][0]

        callback = await client.get(f"/api/v1/auth/oauth/google/callback?code=abc&state={state}")
        assert callback.status_code == 302
        code = _fragment(callback)["code"]
        # The PKCE verifier reached the token endpoint.
        assert handler.seen["token_form"]["code_verifier"][0]

        exchange = await client.post("/api/v1/auth/oauth/exchange", json={"code": code, "client_nonce": NONCE})
        assert exchange.status_code == 200
        body = exchange.json()
        assert body["user"]["email"] == "oauth.trader@example.com"
        assert body["user"]["full_name"] == "OAuth Trader"
        assert body["tokens"]["access_token"]

        replay = await client.post("/api/v1/auth/oauth/exchange", json={"code": code, "client_nonce": NONCE})
        assert replay.status_code == 401

    @pytest.mark.asyncio
    async def test_replayed_state_is_rejected(
        self, client: AsyncClient, oauth_enabled: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_provider(monkeypatch, _provider_handler())
        state = (await _start(client, "google"))["state"][0]

        await client.get(f"/api/v1/auth/oauth/google/callback?code=abc&state={state}")
        again = await client.get(f"/api/v1/auth/oauth/google/callback?code=abc&state={state}")
        assert _fragment(again)["error"] == "state_expired"

    @pytest.mark.asyncio
    async def test_unverified_email_is_refused(
        self, client: AsyncClient, oauth_enabled: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_provider(monkeypatch, _provider_handler(google_verified=False, email="unverified@example.com"))
        state = (await _start(client, "google"))["state"][0]

        callback = await client.get(f"/api/v1/auth/oauth/google/callback?code=abc&state={state}")
        assert _fragment(callback)["error"] == "no_verified_email"

    @pytest.mark.asyncio
    async def test_oauth_never_signs_into_a_password_account_with_that_email(
        self, client: AsyncClient, oauth_enabled: None, monkeypatch: pytest.MonkeyPatch, test_user: Any
    ) -> None:
        """Registration does not verify email ownership, so a password account
        holding someone's address may belong to an attacker who registered it
        first. Signing in with the provider must not hand that account over."""
        _mock_provider(monkeypatch, _provider_handler(email=test_user.email))
        state = (await _start(client, "github"))["state"][0]

        callback = await client.get(f"/api/v1/auth/oauth/github/callback?code=abc&state={state}")
        assert _fragment(callback)["error"] == "password_account_exists"

    @pytest.mark.asyncio
    async def test_repeat_provider_sign_in_reaches_the_same_account(
        self, client: AsyncClient, oauth_enabled: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_provider(monkeypatch, _provider_handler(email="repeat@example.com"))
        ids = []
        for _ in range(2):
            state = (await _start(client, "google"))["state"][0]
            callback = await client.get(f"/api/v1/auth/oauth/google/callback?code=abc&state={state}")
            exchange = await client.post(
                "/api/v1/auth/oauth/exchange", json={"code": _fragment(callback)["code"], "client_nonce": NONCE}
            )
            assert exchange.status_code == 200
            ids.append(exchange.json()["user"]["id"])
        assert ids[0] == ids[1]

    @pytest.mark.asyncio
    async def test_login_code_only_works_in_the_browser_that_started_sign_in(
        self, client: AsyncClient, oauth_enabled: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Login CSRF: an attacker finishes their own sign-in and sends the
        victim the resulting link. The victim's browser holds a different nonce
        (or none), so it must not be signed into the attacker's account."""
        _mock_provider(monkeypatch, _provider_handler(email="attacker@example.com"))
        state = (await _start(client, "google", nonce=NONCE))["state"][0]
        callback = await client.get(f"/api/v1/auth/oauth/google/callback?code=abc&state={state}")
        code = _fragment(callback)["code"]

        victim = await client.post(
            "/api/v1/auth/oauth/exchange", json={"code": code, "client_nonce": "victim-nonce-fedcba9876543210fedcba98"}
        )
        assert victim.status_code == 401

    @pytest.mark.asyncio
    async def test_authorize_requires_a_browser_nonce(self, client: AsyncClient, oauth_enabled: None) -> None:
        response = await client.get("/api/v1/auth/oauth/google/authorize")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_cancelled_consent_returns_a_readable_error(self, client: AsyncClient, oauth_enabled: None) -> None:
        response = await client.get("/api/v1/auth/oauth/google/callback?error=access_denied")
        assert _fragment(response)["error"] == "cancelled"


async def _start_link(client: AsyncClient, provider: str, headers: dict[str, str]) -> str:
    response = await client.post(
        f"/api/v1/auth/oauth/{provider}/link", json={"client_nonce": NONCE}, headers=headers
    )
    assert response.status_code == 200
    return parse_qs(urlparse(response.json()["authorize_url"]).query)["state"][0]


@pytest.mark.integration
class TestOAuthLinking:
    @pytest.mark.asyncio
    async def test_password_user_links_a_provider_and_can_then_sign_in_with_it(
        self,
        client: AsyncClient,
        oauth_enabled: None,
        monkeypatch: pytest.MonkeyPatch,
        test_user: Any,
        auth_headers: dict[str, str],
    ) -> None:
        _mock_provider(monkeypatch, _provider_handler(email=test_user.email))
        state = await _start_link(client, "github", auth_headers)
        callback = await client.get(f"/api/v1/auth/oauth/github/callback?code=abc&state={state}")
        link_code = _fragment(callback)["link_code"]

        done = await client.post(
            "/api/v1/auth/oauth/link/complete",
            json={"code": link_code, "client_nonce": NONCE},
            headers=auth_headers,
        )
        assert done.status_code == 200
        assert done.json()["oauth_provider"] == "github"

        # Provider sign-in now reaches this account.
        state = (await _start(client, "github"))["state"][0]
        signin = await client.get(f"/api/v1/auth/oauth/github/callback?code=abc&state={state}")
        exchange = await client.post(
            "/api/v1/auth/oauth/exchange", json={"code": _fragment(signin)["code"], "client_nonce": NONCE}
        )
        assert exchange.json()["user"]["id"] == str(test_user.id)

    @pytest.mark.asyncio
    async def test_link_requires_the_same_verified_email(
        self,
        client: AsyncClient,
        oauth_enabled: None,
        monkeypatch: pytest.MonkeyPatch,
        auth_headers: dict[str, str],
    ) -> None:
        _mock_provider(monkeypatch, _provider_handler(email="someone.else@example.com"))
        state = await _start_link(client, "google", auth_headers)
        callback = await client.get(f"/api/v1/auth/oauth/google/callback?code=abc&state={state}")

        done = await client.post(
            "/api/v1/auth/oauth/link/complete",
            json={"code": _fragment(callback)["link_code"], "client_nonce": NONCE},
            headers=auth_headers,
        )
        assert done.status_code == 401

    @pytest.mark.asyncio
    async def test_a_forwarded_link_cannot_be_completed_by_another_account(
        self,
        client: AsyncClient,
        oauth_enabled: None,
        monkeypatch: pytest.MonkeyPatch,
        test_user: Any,
        auth_headers: dict[str, str],
        second_user_headers: dict[str, str],
    ) -> None:
        """Pre-hijack via linking: an attacker who pre-registered a victim's
        email starts a link and gets the victim to approve it. The approval
        must not attach the victim's provider account to the attacker's."""
        _mock_provider(monkeypatch, _provider_handler(email=test_user.email))
        state = await _start_link(client, "google", auth_headers)
        callback = await client.get(f"/api/v1/auth/oauth/google/callback?code=abc&state={state}")

        done = await client.post(
            "/api/v1/auth/oauth/link/complete",
            json={"code": _fragment(callback)["link_code"], "client_nonce": NONCE},
            headers=second_user_headers,
        )
        assert done.status_code == 401
