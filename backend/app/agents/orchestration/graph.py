"""
QuantX — Multi-agent orchestration graph (LangGraph).

Wires the specialist agents into a stateful graph:

    START → init → market → technical → quant → risk → synthesis → [execute?] → END

* **init** captures a numeric spot price up front, so the deterministic
  validator always has a reference regardless of model narration.
* each **specialist** runs the shared tool-calling loop with only its role's
  tools and appends a report to shared state.
* **risk** additionally reads the persisted risk state to set a hard ``halted``
  flag.
* **synthesis** reads every report and produces a structured decision, which is
  then re-checked by the deterministic :class:`AIDecisionValidator`; anything
  that fails — or any decision while halted — becomes WAIT.
* **execution** is reached only when mutations are enabled, the decision is
  actionable, and trading is not halted; it places a *paper* order. Live trading
  is never reachable from the graph.

The graph is provider-agnostic: it is handed an :class:`LLMProvider`, so tests
drive it with a scripted provider and production uses Claude or an
OpenAI-compatible model.
"""

from __future__ import annotations

import json
from itertools import pairwise
from typing import TYPE_CHECKING, Any, cast

from langgraph.graph import END, START, StateGraph

from app.agents.llm.base import ChatMessage, LLMProvider
from app.agents.llm.runner import AgentRunner
from app.agents.orchestration.specialists import PIPELINE, RISK_OFFICER, SpecialistSpec
from app.agents.orchestration.state import OrchestrationState, SpecialistReport
from app.agents.validator import AIDecisionValidator
from app.core.logging import get_logger
from app.schemas.agent import AgentDecision

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.agents.tools.base import ToolContext
    from app.agents.tools.registry import ToolRegistry

logger = get_logger(__name__)

# A minimal fixed quantity for the demonstration paper order placed when the
# pipeline reaches the (mutations-enabled) execution step. Real position sizing
# is the risk engine's responsibility, enforced inside the submit_paper_order
# tool; this is only a token amount to exercise the execution path end to end.
DEMO_PAPER_ORDER_QUANTITY = 0.001

SYNTHESIS_SYSTEM_PROMPT = (
    "You are the lead portfolio strategist for QuantX. You are given reports from a market "
    "analyst, a technical analyst, a quant analyst and a risk officer. Weigh them and output a "
    "SINGLE trading decision as strict JSON with keys: action (BUY|SELL|WAIT), confidence (0..1), "
    "reasoning (string), entry_price, stop_loss, take_profit, risk_reward_ratio (numbers or null). "
    "If the risk officer reports a halt, or evidence is weak or conflicting, choose WAIT. "
    "Output ONLY the JSON object, no prose, no code fences."
)


class QuantXOrchestrator:
    """Builds and runs the multi-agent decision graph."""

    def __init__(
        self,
        provider: LLMProvider,
        registry: ToolRegistry,
        ctx: ToolContext,
        *,
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._ctx = ctx
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._graph = self._build()

    # ── graph construction ───────────────────────────────────────────

    def _build(self) -> Any:
        builder = StateGraph(OrchestrationState)
        builder.add_node("init", self._init_node)
        for spec in PIPELINE:
            # The typed async node is a valid LangGraph node; its strict node
            # overloads don't accept our precise signature, so cast at the edge.
            builder.add_node(spec.key, cast("Any", self._make_specialist_node(spec)))
        builder.add_node("synthesis", self._synthesis_node)
        builder.add_node("execution", self._execution_node)

        builder.add_edge(START, "init")
        builder.add_edge("init", PIPELINE[0].key)
        for earlier, later in pairwise(PIPELINE):
            builder.add_edge(earlier.key, later.key)
        builder.add_edge(PIPELINE[-1].key, "synthesis")
        builder.add_conditional_edges(
            "synthesis", self._route_after_synthesis, {"execute": "execution", "end": END}
        )
        builder.add_edge("execution", END)
        return builder.compile()

    async def run(self, symbol: str, account_balance: float = 100_000.0) -> OrchestrationState:
        """Execute the full graph for one symbol and return the final state."""
        initial = OrchestrationState(symbol=symbol.upper(), account_balance=account_balance)
        raw = await self._graph.ainvoke(initial)
        # LangGraph returns the channel values; normalize back to the model.
        return raw if isinstance(raw, OrchestrationState) else OrchestrationState(**raw)

    # ── nodes ─────────────────────────────────────────────────────────

    async def _init_node(self, state: OrchestrationState) -> dict[str, Any]:
        price: float | None = None
        result = await self._registry.invoke("get_price", {"symbol": state.symbol}, self._ctx)
        if result.ok and isinstance(result.data, dict):
            raw_price = result.data.get("price")
            if raw_price is not None:
                price = float(raw_price)
        return {"market_price": price, "log": [*state.log, f"init: price={price}"]}

    def _make_specialist_node(
        self, spec: SpecialistSpec
    ) -> Callable[[OrchestrationState], Awaitable[dict[str, Any]]]:
        async def _node(state: OrchestrationState) -> dict[str, Any]:
            report = await self._run_specialist(spec, state)
            updates: dict[str, Any] = {
                "reports": {**state.reports, spec.key: report},
                "log": [*state.log, f"{spec.key}: {report.tool_calls} tool call(s)"],
            }
            if spec.key == RISK_OFFICER.key:
                updates["halted"] = report.data.get("halted", False)
            return updates

        return _node

    async def _run_specialist(self, spec: SpecialistSpec, state: OrchestrationState) -> SpecialistReport:
        available = [t for t in spec.tool_names if self._registry.get(t) is not None]
        sub = self._registry.subset(available)
        runner = AgentRunner(
            self._provider, sub, self._ctx, temperature=self._temperature, max_tokens=self._max_tokens
        )
        result = await runner.run(spec.system_prompt, spec.task(state.symbol))

        data: dict[str, Any] = {}
        if spec.key == RISK_OFFICER.key:
            risk_state = await self._registry.invoke("get_risk_state", {}, self._ctx)
            if risk_state.ok and isinstance(risk_state.data, dict):
                data["halted"] = bool(risk_state.data.get("halted", False))
        return SpecialistReport(
            agent=spec.key,
            summary=result.final_text,
            tool_calls=len(result.tool_invocations),
            data=data,
        )

    async def _synthesis_node(self, state: OrchestrationState) -> dict[str, Any]:
        prompt = self._build_synthesis_prompt(state)
        response = await self._provider.chat(
            [
                ChatMessage(role="system", content=SYNTHESIS_SYSTEM_PROMPT),
                ChatMessage(role="user", content=prompt),
            ],
            tools=None,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        decision = self._parse_and_validate(response.text, state)
        return {
            "final_decision": decision.model_dump(),
            "log": [*state.log, f"synthesis: {decision.action}"],
        }

    async def _execution_node(self, state: OrchestrationState) -> dict[str, Any]:
        decision = state.final_decision or {}
        side = decision.get("action")
        result = await self._registry.invoke(
            "submit_paper_order",
            {"symbol": state.symbol, "side": side, "quantity": DEMO_PAPER_ORDER_QUANTITY},
            self._ctx,
        )
        order = result.data if (result.ok and isinstance(result.data, dict)) else {"error": result.error}
        return {"executed_order": order, "log": [*state.log, f"execution: ok={result.ok}"]}

    # ── routing & synthesis helpers ───────────────────────────────────

    def _route_after_synthesis(self, state: OrchestrationState) -> str:
        decision = state.final_decision or {}
        actionable = decision.get("action") in {"BUY", "SELL"}
        if self._ctx.allow_mutations and actionable and not state.halted:
            return "execute"
        return "end"

    def _build_synthesis_prompt(self, state: OrchestrationState) -> str:
        lines = [f"Symbol: {state.symbol}", f"Reference price: {state.market_price}", ""]
        for spec in PIPELINE:
            report = state.reports.get(spec.key)
            if report:
                lines.append(f"[{spec.title}] {report.summary}")
        if state.halted:
            lines.append("\nNOTE: Trading is currently HALTED for this account.")
        lines.append("\nProduce the JSON decision now.")
        return "\n".join(lines)

    def _parse_and_validate(self, text: str, state: OrchestrationState) -> AgentDecision:
        try:
            payload = json.loads(_strip_code_fences(text))
            decision = AgentDecision.model_validate(payload)
        except Exception as exc:
            logger.warning("synthesis_parse_failed", error=str(exc))
            return AgentDecision(action="WAIT", confidence=0.0, reasoning=f"Unparseable synthesis: {exc}")

        if state.halted:
            return AgentDecision(action="WAIT", confidence=0.0, reasoning="Trading halted by risk engine.")
        if state.market_price is None:
            return AgentDecision(action="WAIT", confidence=0.0, reasoning="No reference price available.")

        validation = AIDecisionValidator.validate(
            decision=decision,
            current_price=state.market_price,
            account_balance=state.account_balance,
        )
        if not validation.is_valid:
            return AgentDecision(
                action="WAIT",
                confidence=0.0,
                reasoning="Rejected by deterministic validator: " + "; ".join(validation.rejection_reasons),
            )
        return decision


def _strip_code_fences(text: str) -> str:
    """Remove ```json fences a model sometimes wraps JSON in."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s
        if s.endswith("```"):
            s = s[: -3]
    return s.strip()
