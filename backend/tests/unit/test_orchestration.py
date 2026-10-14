"""
QuantX — Multi-agent orchestration tests.

Drives the LangGraph graph with a scripted provider so the full pipeline
(init → 4 specialists → synthesis → optional execution) runs deterministically
without network. Covers: report accumulation, reference-price capture, the
deterministic validator downgrade to WAIT, the mutation-gated execution step,
and that a valid actionable decision with mutations enabled places a paper order.
"""

from __future__ import annotations

import json
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm.base import ChatMessage, LLMProvider, LLMResponse
from app.agents.orchestration import build_orchestrator
from app.agents.tools.base import ToolContext
from app.connectors.binance_client import BinanceClient
from app.models.user import User
from app.schemas.paper_trading import CreatePaperAccountRequest
from app.services.paper_trading_service import PaperTradingService
from tests.conftest import FakeBinanceClient

VALID_BUY = {
    "action": "BUY",
    "confidence": 0.7,
    "reasoning": "Uptrend with supportive momentum.",
    "entry_price": 50_000.0,
    "stop_loss": 49_000.0,
    "take_profit": 52_000.0,
    "risk_reward_ratio": 2.0,
}

INVERTED_STOP_BUY = {**VALID_BUY, "stop_loss": 51_000.0}  # stop above entry for a BUY → invalid


class OrchestrationFakeProvider(LLMProvider):
    """Specialists get a canned summary; synthesis gets the scripted decision.

    The two are told apart by the synthesis system prompt, so no specialist ever
    needs tools and the graph runs without stored candles.
    """

    provider_name = "openai"

    def __init__(self, decision: dict[str, Any]) -> None:
        self._decision = json.dumps(decision)

    @property
    def model(self) -> str:
        return "fake"

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> LLMResponse:
        system = messages[0].content if messages else ""
        if "lead portfolio strategist" in system:
            return LLMResponse(text=self._decision, model="fake")
        return LLMResponse(text="Specialist summary based on available data.", model="fake")


def _ctx(db_session: AsyncSession, user: User, *, allow_mutations: bool) -> ToolContext:
    return ToolContext(
        session=db_session,
        user_id=user.id,
        client=cast(BinanceClient, FakeBinanceClient(price=50_000.0)),
        account_balance=100_000.0,
        allow_mutations=allow_mutations,
    )


async def test_pipeline_runs_all_specialists_and_captures_price(
    db_session: AsyncSession, test_user: User
) -> None:
    provider = OrchestrationFakeProvider(VALID_BUY)
    orch = build_orchestrator(provider, _ctx(db_session, test_user, allow_mutations=False))
    state = await orch.run("BTCUSDT")

    assert set(state.reports) == {"market", "technical", "quant", "risk"}
    assert state.market_price == 50_000.0
    assert state.final_decision is not None
    assert state.final_decision["action"] == "BUY"
    # mutations disabled → no order placed
    assert state.executed_order is None


async def test_invalid_decision_is_downgraded_to_wait(
    db_session: AsyncSession, test_user: User
) -> None:
    provider = OrchestrationFakeProvider(INVERTED_STOP_BUY)
    orch = build_orchestrator(provider, _ctx(db_session, test_user, allow_mutations=False))
    state = await orch.run("BTCUSDT")

    assert state.final_decision is not None
    assert state.final_decision["action"] == "WAIT"
    assert "validator" in state.final_decision["reasoning"].lower()


async def test_execution_gate_blocks_order_without_mutations(
    db_session: AsyncSession, test_user: User
) -> None:
    # Even a valid BUY must not place an order when mutations are disabled.
    provider = OrchestrationFakeProvider(VALID_BUY)
    orch = build_orchestrator(provider, _ctx(db_session, test_user, allow_mutations=False))
    state = await orch.run("BTCUSDT")
    assert state.executed_order is None


async def test_execution_places_paper_order_when_enabled(
    db_session: AsyncSession, test_user: User
) -> None:
    # A real paper account must exist for the order to fill.
    await PaperTradingService(db_session).create_account(
        test_user.id, CreatePaperAccountRequest(name="Agent", initial_balance=100_000.0)
    )
    provider = OrchestrationFakeProvider(VALID_BUY)
    orch = build_orchestrator(provider, _ctx(db_session, test_user, allow_mutations=True))
    state = await orch.run("BTCUSDT")

    assert state.final_decision is not None
    assert state.final_decision["action"] == "BUY"
    assert state.executed_order is not None
    assert state.executed_order.get("status") == "FILLED"
    assert state.executed_order.get("side") == "BUY"
