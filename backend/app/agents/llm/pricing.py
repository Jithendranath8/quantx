"""
QuantX — LLM token-cost estimation.

Shared by the single-shot analyst and anything else that reports what a call
cost. The guiding rule is honesty over completeness: a self-hosted endpoint and
an unpriced third-party model both report **0.0** rather than a fabricated
figure, because the observability layer exists to record what actually happened.
"""

from __future__ import annotations

# USD per 1M tokens, (input, output). Update alongside provider pricing changes.
MODEL_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
}

# Endpoints that bill nothing per token (a model on your own machine).
FREE_ENDPOINT_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal", "ollama")


def is_free_endpoint(base_url: str | None) -> bool:
    """Whether ``base_url`` points at an endpoint that bills nothing per token."""
    if not base_url:
        return False
    return any(host in base_url for host in FREE_ENDPOINT_HOSTS)


def estimate_cost_usd(model: str, usage: dict[str, int], base_url: str | None = None) -> float:
    """Estimate USD cost from token counts and the model's price.

    Returns 0.0 for a self-hosted endpoint and for any model whose price we do
    not know, rather than guessing at a default rate.
    """
    if not usage or is_free_endpoint(base_url):
        return 0.0
    if model not in MODEL_PRICING_PER_MTOK:
        return 0.0
    input_rate, output_rate = MODEL_PRICING_PER_MTOK[model]
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    return round((prompt * input_rate + completion * output_rate) / 1_000_000, 6)
