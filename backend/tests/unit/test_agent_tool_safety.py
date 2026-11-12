"""
QuantX — Agent tool safety tests.

Security audit finding 7: agent routes held a pooled database connection for
the whole model loop. A tool call now ends its transaction when it returns, so
the connection is free while the model is being waited on. A failed call rolls
back, and tells the model the kind of failure without the raw exception text.
"""

from typing import Any

import pytest

from app.agents.tools.base import ToolContext
from app.agents.tools.market_tools import GetPriceTool
from app.core.exceptions import ValidationError


class RecordingSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class PriceClient:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    async def get_price(self, symbol: str) -> float:
        if self._error is not None:
            raise self._error
        return 50_000.0

    async def get_reference_price(self, symbol: str) -> float:
        return await self.get_price(symbol)


def _context(client: Any) -> tuple[ToolContext, RecordingSession]:
    session = RecordingSession()
    return ToolContext(session=session, client=client), session  # type: ignore[arg-type]


@pytest.mark.unit
class TestToolTransactions:
    @pytest.mark.asyncio
    async def test_a_tool_call_releases_the_connection_when_it_returns(self) -> None:
        ctx, session = _context(PriceClient())
        result = await GetPriceTool()({"symbol": "BTCUSDT"}, ctx)
        assert result.ok is True
        assert (session.commits, session.rollbacks) == (1, 0)

    @pytest.mark.asyncio
    async def test_a_failed_tool_call_rolls_back(self) -> None:
        ctx, session = _context(PriceClient(RuntimeError("connection to db.internal:5432 refused")))
        result = await GetPriceTool()({"symbol": "BTCUSDT"}, ctx)
        assert result.ok is False
        assert (session.commits, session.rollbacks) == (0, 1)

    @pytest.mark.asyncio
    async def test_raw_exception_text_is_not_shown_to_the_model(self) -> None:
        ctx, _ = _context(PriceClient(RuntimeError("connection to db.internal:5432 refused")))
        result = await GetPriceTool()({"symbol": "BTCUSDT"}, ctx)
        assert "db.internal" not in (result.error or "")
        assert "RuntimeError" in (result.error or "")

    @pytest.mark.asyncio
    async def test_domain_errors_keep_their_message(self) -> None:
        ctx, _ = _context(PriceClient(ValidationError("Symbol is not listed")))
        result = await GetPriceTool()({"symbol": "BTCUSDT"}, ctx)
        assert "Symbol is not listed" in (result.error or "")


@pytest.mark.unit
class TestExchangeActionGate:
    @pytest.mark.asyncio
    async def test_the_kill_switch_needs_its_own_permission(self) -> None:
        """Enabling paper-order mutations must not also enable signed exchange cancels."""
        from app.agents.tools.trading_tools import ActivateKillSwitchTool

        ctx, _ = _context(PriceClient())
        ctx.allow_mutations = True
        result = await ActivateKillSwitchTool()({"reason": "test"}, ctx)
        assert result.ok is False
        assert "not enabled" in (result.error or "")


@pytest.mark.unit
class TestDecisionValidator:
    def _decision(self, **kwargs: Any) -> Any:
        from app.schemas.agent import AgentDecision

        base = {
            "action": "BUY",
            "confidence": 0.8,
            "reasoning": "test",
            "entry_price": 50_000.0,
            "stop_loss": 49_000.0,
            "take_profit": 52_000.0,
        }
        return AgentDecision.model_construct(**{**base, **kwargs})

    def test_a_sane_decision_passes(self) -> None:
        from app.agents.validator import AIDecisionValidator

        assert AIDecisionValidator.validate(self._decision(), 50_000.0, 100_000.0).is_valid is True

    def test_an_entry_far_from_the_market_is_rejected(self) -> None:
        from app.agents.validator import AIDecisionValidator

        result = AIDecisionValidator.validate(
            self._decision(entry_price=1.0, stop_loss=0.5, take_profit=2.0), 50_000.0, 100_000.0
        )
        assert result.is_valid is False
        assert any("from the market" in r for r in result.rejection_reasons)

    @pytest.mark.parametrize("field", ["entry_price", "stop_loss", "take_profit"])
    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), -5.0])
    def test_non_finite_levels_are_rejected(self, field: str, value: float) -> None:
        from app.agents.validator import AIDecisionValidator

        result = AIDecisionValidator.validate(self._decision(**{field: value}), 50_000.0, 100_000.0)
        assert result.is_valid is False
