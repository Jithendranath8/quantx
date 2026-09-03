"""
QuantX — Integration Tests for the AI Agent Endpoint.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestAgentEndpoint:
    """Agent analysis over HTTP."""

    @pytest.mark.asyncio
    async def test_analyze_returns_a_decision(
        self, client: AsyncClient, auth_headers: dict, seeded_candles: int
    ) -> None:
        """A decision is always structurally valid, even with no API key."""
        response = await client.get(
            "/api/v1/agent/analyze?symbol=BTCUSDT", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action"] in {"BUY", "SELL", "WAIT"}
        assert "confidence" in data
        assert "reasoning" in data

    @pytest.mark.asyncio
    async def test_analyze_waits_without_a_configured_model(
        self, client: AsyncClient, auth_headers: dict, seeded_candles: int
    ) -> None:
        """With no OpenAI key the agent degrades to WAIT rather than erroring."""
        data = (
            await client.get("/api/v1/agent/analyze?symbol=BTCUSDT", headers=auth_headers)
        ).json()
        assert data["action"] == "WAIT"
        assert data["confidence"] == 0.0
