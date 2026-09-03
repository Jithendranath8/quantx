"""
QuantX — Integration Tests for Auth API Endpoints.

Tests the full HTTP request/response cycle through FastAPI test client.
Uses fixtures from conftest.py for database and client setup.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestRegisterEndpoint:
    """Integration tests for POST /api/v1/auth/register."""

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient) -> None:
        """Successful registration should return 201 with user and tokens."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@quantx.io",
                "username": "newuser",
                "password": "StrongP@ss1",
                "full_name": "New User",
            },
        )
        assert response.status_code == 201

        data = response.json()
        assert data["user"]["email"] == "newuser@quantx.io"
        assert data["user"]["username"] == "newuser"
        assert data["user"]["is_active"] is True
        assert "access_token" in data["tokens"]
        assert "refresh_token" in data["tokens"]

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient) -> None:
        """Duplicate email should return 409."""
        payload = {
            "email": "dupe@quantx.io",
            "username": "user1",
            "password": "StrongP@ss1",
        }
        await client.post("/api/v1/auth/register", json=payload)

        payload["username"] = "user2"
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client: AsyncClient) -> None:
        """Invalid email format should return 422."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "not-an-email",
                "username": "validuser",
                "password": "StrongP@ss1",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_short_username(self, client: AsyncClient) -> None:
        """Username shorter than 3 chars should return 422."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "short@quantx.io",
                "username": "ab",
                "password": "StrongP@ss1",
            },
        )
        assert response.status_code == 422


@pytest.mark.integration
class TestLoginEndpoint:
    """Integration tests for POST /api/v1/auth/login."""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient) -> None:
        """Login with valid credentials should return 200 with tokens."""
        # Register first
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "loginuser@quantx.io",
                "username": "loginuser",
                "password": "StrongP@ss1",
            },
        )

        # Login
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "loginuser@quantx.io",
                "password": "StrongP@ss1",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data["tokens"]

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient) -> None:
        """Wrong password should return 401."""
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "wrongpw@quantx.io",
                "username": "wrongpw",
                "password": "StrongP@ss1",
            },
        )

        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "wrongpw@quantx.io",
                "password": "WrongPassword1",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_email(self, client: AsyncClient) -> None:
        """Non-existent email should return 401."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "noone@quantx.io",
                "password": "AnyPassword1",
            },
        )
        assert response.status_code == 401


@pytest.mark.integration
class TestMeEndpoint:
    """Integration tests for GET /api/v1/auth/me."""

    @pytest.mark.asyncio
    async def test_get_me_authenticated(self, client: AsyncClient, auth_headers: dict) -> None:
        """Authenticated request should return user profile."""
        response = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "testuser@quantx.io"
        assert data["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_get_me_unauthenticated(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_invalid_token(self, client: AsyncClient) -> None:
        """Invalid token should return 401."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert response.status_code == 401


@pytest.mark.integration
class TestRefreshEndpoint:
    """Integration tests for POST /api/v1/auth/refresh."""

    @pytest.mark.asyncio
    async def test_refresh_success(self, client: AsyncClient) -> None:
        """Valid refresh token should return new token pair."""
        # Register to get tokens
        reg_response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "refresh@quantx.io",
                "username": "refreshuser",
                "password": "StrongP@ss1",
            },
        )
        refresh_token = reg_response.json()["tokens"]["refresh_token"]

        # Refresh
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        # Token should be rotated
        assert data["refresh_token"] != refresh_token


@pytest.mark.integration
class TestHealthEndpoint:
    """Integration tests for GET /health."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient) -> None:
        """Health endpoint should return 200."""
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
