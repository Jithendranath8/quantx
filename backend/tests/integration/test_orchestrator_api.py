"""
QuantX — Orchestration API integration tests.

Exercise POST /api/v1/agent/orchestrate end-to-end through the app, with the LLM
provider and Binance client replaced by fakes so no network is touched. Covers
the happy path, the "no provider configured" guard, and auth.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from httpx import AsyncClient

import app.api.v1.endpoints.orchestrator as orch_endpoint
from app.agents.llm.base import ChatMessage, LLMProvider, LLMResponse
from tests.conftest import FakeBinanceClient

VALID_BUY = {
    "action": "BUY",
    "confidence": 0.7,
    "reasoning": "Trend and momentum align.",
    "entry_price": 50_000.0,
    "stop_loss": 49_000.0,
    "take_profit": 52_000.0,
    "risk_reward_ratio": 2.0,
}


class _FakeProvider(LLMProvider):
    provider_name = "openai"

    def __init__(self, decision: dict[str, Any]) -> None:
        self._decision = json.dumps(decision)

    @property
    def model(self) -> str:
        return "fake"

    async def chat(self, messages, tools=None, *, temperature=0.1, max_tokens=1200):  # type: ignore[no-untyped-def]
        system = messages[0].content if messages else ""
        if "lead portfolio strategist" in system:
            return LLMResponse(text=self._decision, model="fake")
        return LLMResponse(text="Specialist summary.", model="fake")


def _configure(monkeypatch: pytest.MonkeyPatch, *, provider: bool = True) -> None:
    monkeypatch.setattr(orch_endpoint, "get_binance_client", lambda: FakeBinanceClient(price=50_000.0))
    monkeypatch.setattr(orch_endpoint, "build_provider", lambda *a, **k: _FakeProvider(VALID_BUY))
    settings = orch_endpoint.get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    if provider:
        monkeypatch.setattr(settings, "openai_base_url", "http://fake:11434/v1")
    else:
        monkeypatch.setattr(settings, "openai_base_url", None)
        monkeypatch.setattr(settings, "openai_api_key", "")


async def test_orchestrate_returns_decision_and_reports(
    client: AsyncClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure(monkeypatch)
    resp = await client.post("/api/v1/agent/orchestrate?symbol=BTCUSDT", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "BTCUSDT"
    assert body["decision"]["action"] == "BUY"
    assert set(body["reports"]) == {"market", "technical", "quant", "risk"}
    assert body["market_price"] == 50_000.0
    # execute defaults to false → no order placed
    assert body["executed_order"] is None


async def test_orchestrate_requires_configured_provider(
    client: AsyncClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure(monkeypatch, provider=False)
    resp = await client.post("/api/v1/agent/orchestrate?symbol=BTCUSDT", headers=auth_headers)
    assert resp.status_code == 503


async def test_orchestrate_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/agent/orchestrate?symbol=BTCUSDT")
    assert resp.status_code in (401, 403)
