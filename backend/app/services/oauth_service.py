"""
QuantX — OAuth 2.0 sign-in (Authorization Code flow with PKCE).

Flow:
1. ``start`` creates a single-use ``state`` and a PKCE verifier, keeps them in
   Redis for a few minutes, and returns the provider's consent URL.
2. The provider redirects back to ``complete`` with ``code`` and ``state``. The
   state is consumed (GETDEL, so a replayed callback fails), the code is
   exchanged with the verifier, and the provider's *verified* email is fetched.
3. ``complete`` does not put tokens in a URL. It stores the user id under a
   short-lived one-time login code that the SPA receives in the URL fragment
   and trades for the usual JWT pair through ``redeem``.

Both the state and the login code are bound to a random nonce the SPA keeps in
``sessionStorage`` and sends at the start and at the exchange. Without that, an
attacker could finish their own sign-in and send a victim the callback link (or
the ``/auth/callback#code=`` link), signing the victim into the attacker's
account. Only the browser that began the flow holds the nonce.

Accounts are matched on the verified email address, so signing in with Google
or GitHub reaches the same account as the email/password login.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, NotFoundError, OAuthSignInError
from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from redis.asyncio import Redis

logger = get_logger(__name__)

STATE_TTL_SECONDS = 600
LOGIN_CODE_TTL_SECONDS = 60
HTTP_TIMEOUT_SECONDS = 10.0
_STATE_KEY = "oauth:state:{}"
_LOGIN_KEY = "oauth:login:{}"
_LINK_KEY = "oauth:link:{}"


@dataclass(frozen=True)
class OAuthProvider:
    """Static endpoints and scopes of one identity provider."""

    name: str
    label: str
    authorize_url: str
    token_url: str
    scope: str


PROVIDERS: dict[str, OAuthProvider] = {
    "google": OAuthProvider(
        name="google",
        label="Google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scope="openid email profile",
    ),
    "github": OAuthProvider(
        name="github",
        label="GitHub",
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        scope="read:user user:email",
    ),
}


@dataclass(frozen=True)
class OAuthIdentity:
    """What QuantX needs from a provider: a verified email and a display name."""

    email: str
    full_name: str | None


def _credentials(provider: str) -> tuple[str, str]:
    settings = get_settings()
    return (
        getattr(settings, f"oauth_{provider}_client_id", ""),
        getattr(settings, f"oauth_{provider}_client_secret", ""),
    )


def enabled_providers() -> list[OAuthProvider]:
    """Providers whose client id and secret are both configured."""
    return [p for p in PROVIDERS.values() if all(_credentials(p.name))]


def _provider(name: str) -> OAuthProvider:
    provider = PROVIDERS.get(name)
    if provider is None or not all(_credentials(name)):
        raise NotFoundError("OAuth provider", name)
    return provider


def callback_url(provider: str) -> str:
    """The redirect URI registered with the provider."""
    base = get_settings().public_api_url.rstrip("/")
    return f"{base}/api/v1/auth/oauth/{provider}/callback"


def _digest(value: str) -> str:
    """Store nonces hashed, so Redis contents alone cannot complete a sign-in."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class OAuthService:
    """Runs the provider dance; account creation is left to AuthService."""

    def __init__(self, redis: Redis, http: httpx.AsyncClient | None = None) -> None:  # type: ignore[type-arg]
        self._redis = redis
        self._http = http

    async def start(self, provider_name: str, client_nonce: str, link_user_id: str | None = None) -> str:
        """Return the provider consent URL for a fresh, single-use state.

        Every flow carries the starting browser's nonce. A link also carries
        the id of the authenticated user who started it; the callback then
        issues a link code instead of a login code.
        """
        provider = _provider(provider_name)
        client_id, _ = _credentials(provider.name)
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        await self._redis.set(
            _STATE_KEY.format(state),
            json.dumps(
                {
                    "provider": provider.name,
                    "verifier": verifier,
                    "nonce": _digest(client_nonce),
                    "link_user_id": link_user_id,
                }
            ),
            ex=STATE_TTL_SECONDS,
        )
        params = {
            "client_id": client_id,
            "redirect_uri": callback_url(provider.name),
            "response_type": "code",
            "scope": provider.scope,
            "state": state,
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
        }
        if provider.name == "google":
            params["prompt"] = "select_account"
        return f"{provider.authorize_url}?{urlencode(params)}"

    async def identify(self, provider_name: str, code: str, state: str) -> tuple[OAuthIdentity, dict[str, Any]]:
        """Consume the state, exchange the code, and fetch the verified identity.

        Returns:
            The identity and the stored state: its ``nonce`` digest (sign-in)
            or ``link_user_id`` (link) decides what the callback does next.
        """
        provider = _provider(provider_name)
        raw = await self._redis.getdel(_STATE_KEY.format(state))
        if raw is None:
            raise OAuthSignInError("state_expired", "Sign-in link expired or was already used. Please try again.")
        stored = json.loads(raw)
        if stored.get("provider") != provider.name:
            raise OAuthSignInError("state_mismatch", "Sign-in state does not match the provider.")

        async with self._client() as http:
            access_token = await self._exchange(http, provider, code, stored["verifier"])
            if provider.name == "google":
                identity = await self._google_identity(http, access_token)
            else:
                identity = await self._github_identity(http, access_token)
        return identity, stored

    async def issue_login_code(self, user_id: str, nonce_digest: str) -> str:
        """Store a one-time code the SPA can trade for tokens, bound to its nonce."""
        code = secrets.token_urlsafe(32)
        await self._redis.set(
            _LOGIN_KEY.format(code),
            json.dumps({"user_id": user_id, "nonce": nonce_digest}),
            ex=LOGIN_CODE_TTL_SECONDS,
        )
        return code

    async def issue_link_code(self, user_id: str, provider: str, email: str, nonce_digest: str) -> str:
        """Store a pending link that only its starting user and browser can complete."""
        code = secrets.token_urlsafe(32)
        await self._redis.set(
            _LINK_KEY.format(code),
            json.dumps({"user_id": user_id, "provider": provider, "email": email, "nonce": nonce_digest}),
            ex=LOGIN_CODE_TTL_SECONDS,
        )
        return code

    async def redeem_link_code(self, code: str, client_nonce: str, user_id: str) -> tuple[str, str]:
        """Consume a pending link for the signed-in user; returns (provider, verified email).

        Both checks matter: the nonce proves this browser started the link, and
        the user id proves the person signed in here is the one who asked. A
        consent link forwarded to someone else fails both.
        """
        raw = await self._redis.getdel(_LINK_KEY.format(code))
        if raw is None:
            raise AuthenticationError("Link code expired or was already used. Please try again.")
        stored = json.loads(raw)
        if not hmac.compare_digest(str(stored.get("nonce", "")), _digest(client_nonce)) or str(
            stored.get("user_id")
        ) != str(user_id):
            logger.warning("oauth_link_code_mismatch")
            raise AuthenticationError("This link was started in a different browser or account. Please try again.")
        return str(stored["provider"]), str(stored["email"])

    async def redeem_login_code(self, code: str, client_nonce: str) -> str:
        """Return the user id behind a one-time code, consuming it.

        The code is consumed even when the nonce does not match, so a code
        delivered to the wrong browser cannot be retried until it works.
        """
        raw = await self._redis.getdel(_LOGIN_KEY.format(code))
        if raw is None:
            raise AuthenticationError("Sign-in code expired or was already used. Please sign in again.")
        stored = json.loads(raw)
        if not hmac.compare_digest(str(stored.get("nonce", "")), _digest(client_nonce)):
            logger.warning("oauth_login_code_nonce_mismatch")
            raise AuthenticationError("This sign-in was started in a different browser. Please sign in again.")
        return str(stored["user_id"])

    # ── Provider calls ───────────────────────────────────────────────

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[httpx.AsyncClient]:
        # An injected client (tests) is owned by the caller and is not closed.
        if self._http is not None:
            yield self._http
            return
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http:
            yield http

    @staticmethod
    async def _exchange(http: httpx.AsyncClient, provider: OAuthProvider, code: str, verifier: str) -> str:
        client_id, client_secret = _credentials(provider.name)
        response = await http.post(
            provider.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": callback_url(provider.name),
                "client_id": client_id,
                "client_secret": client_secret,
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json"},
        )
        body: dict[str, Any] = response.json() if response.content else {}
        token = body.get("access_token")
        if response.status_code != 200 or not token:
            logger.warning("oauth_token_exchange_failed", provider=provider.name, status=response.status_code)
            raise OAuthSignInError("provider_rejected", f"{provider.label} rejected the sign-in. Please try again.")
        return str(token)

    @staticmethod
    async def _google_identity(http: httpx.AsyncClient, token: str) -> OAuthIdentity:
        response = await http.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {token}"},
        )
        info = response.json()
        if response.status_code != 200 or not info.get("email") or not info.get("email_verified"):
            raise OAuthSignInError("no_verified_email", "Google did not return a verified email address.")
        return OAuthIdentity(email=str(info["email"]).lower(), full_name=info.get("name"))

    @staticmethod
    async def _github_identity(http: httpx.AsyncClient, token: str) -> OAuthIdentity:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        user = await http.get("https://api.github.com/user", headers=headers)
        emails = await http.get("https://api.github.com/user/emails", headers=headers)
        if user.status_code != 200 or emails.status_code != 200:
            raise OAuthSignInError("profile_unreadable", "GitHub profile could not be read.")
        # The public profile email may be absent or unverified; only the
        # primary, verified address is trusted to identify the account.
        primary = next((e for e in emails.json() if e.get("primary") and e.get("verified")), None)
        if primary is None:
            raise OAuthSignInError("no_verified_email", "Your GitHub account has no verified primary email.")
        profile = user.json()
        return OAuthIdentity(email=str(primary["email"]).lower(), full_name=profile.get("name") or profile.get("login"))

