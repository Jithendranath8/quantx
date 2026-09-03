"""
QuantX — Integration Tests for the Health Center.

The health report must be capable of reporting a problem. The previous version
returned literal strings ("redis_cache": "CONNECTED", freshness 0.4s) for every
subsystem except the database.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestHealthEndpoints:
    """Liveness, readiness, and the full subsystem report."""

    @pytest.mark.asyncio
    async def test_liveness_is_shallow(self, client: AsyncClient) -> None:
        """The liveness probe touches no dependency."""
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_readiness_reports_each_datastore(self, client: AsyncClient) -> None:
        """Readiness names what it actually checked."""
        response = await client.get("/ready")
        assert response.status_code in {200, 503}
        checks = response.json()["checks"]
        assert set(checks) == {"database", "redis"}

    @pytest.mark.asyncio
    async def test_system_health_measures_subsystems(
        self, client: AsyncClient, auth_headers: dict, stub_binance
    ) -> None:
        """Every subsystem carries a measured healthy flag, not a fixed label."""
        response = await client.get("/api/v1/health/system", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        subsystems = data["subsystems"]
        assert subsystems["api_server"]["status"] == "ONLINE"
        assert subsystems["database"]["healthy"] is True
        assert "latency_ms" in subsystems["database"]

        # Every entry reports a boolean verdict that can be False.
        for name, entry in subsystems.items():
            assert "healthy" in entry, f"{name} has no health verdict"
            assert isinstance(entry["healthy"], bool)

        # The stream is disabled in tests, so it must not claim to be streaming.
        assert subsystems["market_data_stream"]["healthy"] is False
        assert subsystems["market_data_stream"]["enabled"] is False

    @pytest.mark.asyncio
    async def test_system_health_reflects_a_tripped_breaker(
        self, client: AsyncClient, auth_headers: dict, stub_binance
    ) -> None:
        """Halting trading shows up in the health report."""
        await client.post("/api/v1/risk/circuit-breaker/toggle?active=true", headers=auth_headers)
        response = await client.get("/api/v1/health/system", headers=auth_headers)
        risk = response.json()["subsystems"]["risk_engine"]
        assert risk["status"] == "CIRCUIT_BREAKER_HALT"
        assert risk["healthy"] is False


@pytest.mark.integration
class TestAIServiceHealth:
    """A configured key is not a working key.

    Reporting OPERATIONAL on key presence alone produced a probe that could not
    detect the most common real failure: a key that is valid but out of credit,
    revoked, or rate limited.
    """

    @pytest.mark.asyncio
    async def test_no_key_reports_not_configured(
        self, client: AsyncClient, auth_headers: dict, stub_binance
    ) -> None:
        """Tests run without an OpenAI key, and the probe says so."""
        response = await client.get("/api/v1/health/system", headers=auth_headers)
        ai = response.json()["subsystems"]["ai_service"]
        assert ai["status"] == "NOT_CONFIGURED"
        assert ai["healthy"] is False

    @pytest.mark.asyncio
    async def test_all_wait_decisions_report_degraded(
        self, client: AsyncClient, auth_headers: dict, db_session, stub_binance, monkeypatch
    ) -> None:
        """An all-WAIT window is the signature of a failing provider call."""
        from datetime import UTC, datetime

        from app.core.config import get_settings
        from app.models.master_models import AIDecisionLog

        monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test-key")

        for _ in range(3):
            db_session.add(
                AIDecisionLog(
                    symbol="BTCUSDT",
                    model="gpt-4o",
                    confidence=0.0,
                    action="WAIT",
                    latency_ms=10,
                    token_usage={},
                    estimated_cost_usd=0.0,
                    input_snapshot={},
                    output_decision={"action": "WAIT", "reasoning": "AI Agent error"},
                    timestamp=datetime.now(UTC),
                )
            )
        await db_session.commit()

        response = await client.get("/api/v1/health/system", headers=auth_headers)
        ai = response.json()["subsystems"]["ai_service"]
        assert ai["status"] == "DEGRADED"
        assert ai["healthy"] is False
        assert ai["recent_wait_decisions"] == 3
        assert "quota" in ai["detail"]

    @pytest.mark.asyncio
    async def test_a_real_decision_reports_operational(
        self, client: AsyncClient, auth_headers: dict, db_session, stub_binance, monkeypatch
    ) -> None:
        """One successful directional call proves the provider works."""
        from datetime import UTC, datetime

        from app.core.config import get_settings
        from app.models.master_models import AIDecisionLog

        monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test-key")

        db_session.add(
            AIDecisionLog(
                symbol="BTCUSDT",
                model="gpt-4o",
                confidence=0.8,
                action="BUY",
                latency_ms=400,
                token_usage={"total_tokens": 500},
                estimated_cost_usd=0.002,
                input_snapshot={},
                output_decision={"action": "BUY", "entry_price": 50000.0},
                timestamp=datetime.now(UTC),
            )
        )
        await db_session.commit()

        response = await client.get("/api/v1/health/system", headers=auth_headers)
        ai = response.json()["subsystems"]["ai_service"]
        assert ai["status"] == "OPERATIONAL"
        assert ai["healthy"] is True
