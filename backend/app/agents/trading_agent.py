"""
QuantX — OpenAI AI Trading Agent.

Sends structured market JSON to an OpenAI chat model and parses a structured
BUY/SELL/WAIT decision with stop loss, take profit, and reasoning.

The agent reports its own latency, token usage, and estimated cost so the
observability layer can record what actually happened instead of a constant.
"""

import json
import time

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.agents.prompt_builder import PromptBuilder
from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.agent import AgentDecision, AgentMarketContext

logger = get_logger(__name__)

# Local models on modest hardware are slow; give them room before giving up.
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"
REQUEST_TIMEOUT_SECONDS = 90.0
# Enough for the decision object plus a sentence of reasoning. Small local
# models are more verbose than cloud ones, and a truncated response is
# unparseable JSON rather than a partial answer.
MAX_COMPLETION_TOKENS = 1200

# USD per 1M tokens, (input, output). Update alongside provider pricing
# changes.
MODEL_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
}
_DEFAULT_PRICING = MODEL_PRICING_PER_MTOK["gpt-4o"]

# Endpoints that cost nothing per token. Reporting an inferred dollar figure
# for a model running on your own machine would be a fabricated number, which
# is exactly what the observability layer exists to avoid.
FREE_ENDPOINT_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal", "ollama")


class AgentAnalysis(BaseModel):
    """A decision plus the operational metadata of the call that produced it."""

    decision: AgentDecision
    model: str
    latency_ms: int
    token_usage: dict[str, int] = Field(default_factory=dict)
    estimated_cost_usd: float = 0.0
    succeeded: bool = True
    error: str | None = None


class AITradingAgent:
    """AI Trading Agent calling OpenAI for structured decision synthesis."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.model = model or settings.openai_model
        self.base_url = base_url if base_url is not None else settings.openai_base_url

        # A self-hosted endpoint needs no credential, so a base_url alone is
        # enough to construct the client. The SDK still requires a non-empty
        # api_key string, hence the placeholder.
        if self.api_key or self.base_url:
            self.client = AsyncOpenAI(
                api_key=self.api_key or "not-required",
                # Passing the default explicitly rather than None: the SDK
                # falls back to reading OPENAI_BASE_URL from the environment,
                # and .env.example ships that key blank. An empty value there
                # would otherwise leave the client pointing at no host at all.
                base_url=self.base_url or OPENAI_DEFAULT_BASE_URL,
                timeout=REQUEST_TIMEOUT_SECONDS,
                max_retries=1,
            )
        else:
            self.client = None

    async def analyze(self, context: AgentMarketContext) -> AgentAnalysis:
        """Send market context to the model and parse a structured decision.

        Never raises: an unavailable or malformed model response degrades to a
        WAIT decision, because a trading loop must not act on an exception.
        """
        started = time.perf_counter()

        if self.client is None:
            logger.warning("ai_provider_not_configured", symbol=context.symbol)
            return self._failure(
                context,
                "No AI provider configured. Set OPENAI_API_KEY, or OPENAI_BASE_URL "
                "for a local or alternative OpenAI-compatible endpoint.",
                started,
            )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": PromptBuilder.SYSTEM_PROMPT},
                    {"role": "user", "content": PromptBuilder.build_user_prompt(context)},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,  # Low temperature for deterministic decisions
                max_tokens=MAX_COMPLETION_TOKENS,
            )
        except Exception as e:
            logger.error("openai_agent_request_failed", error=str(e), symbol=context.symbol)
            return self._failure(context, f"AI Agent error: {e}", started)

        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = self._extract_usage(response)

        raw_content = response.choices[0].message.content if response.choices else None
        if not raw_content:
            return self._failure(context, "Empty response from OpenAI", started, usage=usage)

        try:
            decision = AgentDecision.model_validate(json.loads(raw_content))
        except Exception as e:
            logger.error("openai_agent_parse_failed", error=str(e), symbol=context.symbol)
            return self._failure(context, f"Unparseable model output: {e}", started, usage=usage)

        return AgentAnalysis(
            decision=decision,
            model=self.model,
            latency_ms=latency_ms,
            token_usage=usage,
            estimated_cost_usd=self._estimate_cost(usage),
            succeeded=True,
        )

    # ── Internals ────────────────────────────────────────────────────

    @staticmethod
    def _extract_usage(response: object) -> dict[str, int]:
        """Pull token counts off the response, tolerating a missing usage block."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return {}
        return {
            "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        }

    def _is_free_endpoint(self) -> bool:
        """Whether this endpoint bills per token."""
        if not self.base_url:
            return False
        return any(host in self.base_url for host in FREE_ENDPOINT_HOSTS)

    def _estimate_cost(self, usage: dict[str, int]) -> float:
        """Estimate USD cost from token counts and the model's price.

        Returns 0.0 for a self-hosted endpoint, and for any model whose price
        we do not know rather than guessing at the gpt-4o rate.
        """
        if not usage or self._is_free_endpoint():
            return 0.0
        if self.model not in MODEL_PRICING_PER_MTOK:
            # An unknown model on a third-party endpoint: report no cost rather
            # than a confidently wrong one.
            return 0.0
        input_rate, output_rate = MODEL_PRICING_PER_MTOK.get(self.model, _DEFAULT_PRICING)
        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        return round((prompt * input_rate + completion * output_rate) / 1_000_000, 6)

    def _failure(
        self,
        context: AgentMarketContext,
        reason: str,
        started: float,
        usage: dict[str, int] | None = None,
    ) -> AgentAnalysis:
        """Build a safe WAIT analysis for any failure path."""
        return AgentAnalysis(
            decision=AgentDecision(
                action="WAIT",
                confidence=0.0,
                reasoning=f"Default to WAIT. Reason: {reason}",
                entry_price=None,
                stop_loss=None,
                take_profit=None,
                invalidation_level=None,
                risk_reward_ratio=None,
            ),
            model=self.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            token_usage=usage or {},
            estimated_cost_usd=self._estimate_cost(usage or {}),
            succeeded=False,
            error=reason,
        )
