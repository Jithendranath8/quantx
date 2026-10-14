"""
QuantX — Provider-agnostic LLM runtime.

Normalized message/response types, two concrete providers (Anthropic native
tool use and any OpenAI-compatible endpoint), a factory that resolves the
configured preference, and the bounded tool-calling loop (:class:`AgentRunner`)
that turns a model plus a tool registry into an agent.
"""

from __future__ import annotations

from app.agents.llm.base import (
    ChatMessage,
    LLMProvider,
    LLMResponse,
    LLMUsage,
    ToolCall,
)
from app.agents.llm.factory import build_provider
from app.agents.llm.runner import AgentRunner, AgentRunResult, ToolInvocation

__all__ = [
    "ChatMessage",
    "LLMProvider",
    "LLMResponse",
    "LLMUsage",
    "ToolCall",
    "build_provider",
    "AgentRunner",
    "AgentRunResult",
    "ToolInvocation",
]
