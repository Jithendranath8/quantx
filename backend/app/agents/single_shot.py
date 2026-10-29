"""
QuantX — Single-shot AI analyst.

One structured BUY/SELL/WAIT decision from a single LLM call (no tools). This is
the cheap counterpart to the multi-agent orchestration graph, and both now sit
on the **same** provider-agnostic runtime (:mod:`app.agents.llm`): it works
against Anthropic Claude or any OpenAI-compatible endpoint through one provider,
shares the deterministic validator, and reports its own latency, token usage and
estimated cost for observability.

Never raises: an unavailable or malformed model response degrades to a WAIT
decision, because a trading loop must not act on an exception.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, Field

from app.agents.llm.base import ChatMessage, LLMProvider
from app.agents.llm.pricing import estimate_cost_usd
from app.agents.parsing import parse_agent_decision
from app.agents.prompt_builder import PromptBuilder
from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.agent import AgentDecision, AgentMarketContext

logger = get_logger(__name__)

# Enough for the decision object plus a sentence of reasoning. Small local
# models are more verbose, and a truncated response is unparseable JSON rather
# than a partial answer.
MAX_DECISION_TOKENS = 1200

# Reasoning prefix of the safe WAIT returned when the call itself failed. The
# health check uses it to tell a failed provider call apart from a model that
# genuinely chose to wait.
FALLBACK_REASONING_PREFIX = "Default to WAIT. Reason:"


class AgentAnalysis(BaseModel):
    """A decision plus the operational metadata of the call that produced it."""

    decision: AgentDecision
    model: str
    latency_ms: int
    token_usage: dict[str, int] = Field(default_factory=dict)
    estimated_cost_usd: float = 0.0
    succeeded: bool = True
    error: str | None = None


class SingleShotAnalyst:
    """Produces one validated-elsewhere decision from a single provider call."""

    def __init__(self, provider: LLMProvider | None, *, base_url: str | None = None) -> None:
        self._provider = provider
        # base_url drives free-endpoint cost detection; model names the price.
        self._base_url = base_url
        self._model = provider.model if provider is not None else get_settings().openai_model

    async def analyze(self, context: AgentMarketContext) -> AgentAnalysis:
        """Send market context to the model and parse a structured decision."""
        started = time.perf_counter()

        if self._provider is None:
            logger.warning("ai_provider_not_configured", symbol=context.symbol)
            return self._wait(
                "No AI provider configured. Set ANTHROPIC_API_KEY, or OPENAI_API_KEY / "
                "OPENAI_BASE_URL for a local or OpenAI-compatible endpoint.",
                started,
            )

        try:
            response = await self._provider.chat(
                [
                    ChatMessage(role="system", content=PromptBuilder.SYSTEM_PROMPT),
                    ChatMessage(role="user", content=PromptBuilder.build_user_prompt(context)),
                ],
                tools=None,
                temperature=0.1,
                max_tokens=MAX_DECISION_TOKENS,
            )
        except Exception as exc:
            logger.error("single_shot_request_failed", error=str(exc), symbol=context.symbol)
            return self._wait(f"AI Agent error: {exc}", started)

        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        }

        if not response.text.strip():
            return self._wait("Empty response from model", started, usage)

        try:
            decision = parse_agent_decision(response.text)
        except Exception as exc:
            logger.error("single_shot_parse_failed", error=str(exc), symbol=context.symbol)
            return self._wait(f"Unparseable model output: {exc}", started, usage)

        return AgentAnalysis(
            decision=decision,
            model=response.model or self._model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            token_usage=usage,
            estimated_cost_usd=estimate_cost_usd(self._model, usage, self._base_url),
            succeeded=True,
        )

    def _wait(
        self, reason: str, started: float, usage: dict[str, int] | None = None
    ) -> AgentAnalysis:
        """Build a safe WAIT analysis for any failure path."""
        return AgentAnalysis(
            decision=AgentDecision(
                action="WAIT",
                confidence=0.0,
                reasoning=f"{FALLBACK_REASONING_PREFIX} {reason}",
            ),
            model=self._model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            token_usage=usage or {},
            estimated_cost_usd=estimate_cost_usd(self._model, usage or {}, self._base_url),
            succeeded=False,
            error=reason,
        )
