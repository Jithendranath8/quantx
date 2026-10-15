"""
QuantX — LLM provider factory.

Resolves configuration (including the "auto" preference) into a concrete
:class:`~app.agents.llm.base.LLMProvider`. This is the one place that knows how
the string setting maps to a class, so the rest of the system selects a backend
by intent, not by import.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_settings

if TYPE_CHECKING:
    from app.agents.llm.base import LLMProvider


def build_provider(name: str | None = None) -> LLMProvider:
    """Construct the configured (or named) provider.

    Args:
        name: Override the configured provider. When omitted, uses
            ``settings.resolved_llm_provider`` ("auto" resolved to a backend).
    """
    settings = get_settings()
    choice = (name or settings.resolved_llm_provider).strip().lower()

    if choice == "anthropic":
        from app.agents.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    if choice == "openai":
        from app.agents.llm.openai_provider import OpenAIProvider

        return OpenAIProvider()

    raise ValueError(f"Unknown LLM provider {choice!r}. Use 'anthropic' or 'openai'.")
