"""
QuantX — Provider-agnostic LLM runtime: core types and interface.

The agent runtime must drive either Anthropic (native tool use) or any
OpenAI-compatible endpoint (function calling) without the orchestration layer
knowing which. These normalized types are the contract between the two: a
provider translates them to and from its own wire format, and the tool-calling
loop (:mod:`app.agents.llm.runner`) only ever sees these.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "tool"]


class ToolCall(BaseModel):
    """A model's request to invoke one tool."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    """One turn in the conversation, normalized across providers.

    * ``assistant`` turns may carry ``tool_calls``.
    * ``tool`` turns carry the result of one call and reference it by
      ``tool_call_id``.
    """

    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


class LLMUsage(BaseModel):
    """Token accounting for one provider call."""

    input_tokens: int = 0
    output_tokens: int = 0


class LLMResponse(BaseModel):
    """A single provider response, normalized.

    ``tool_calls`` being non-empty is how the loop knows the model wants to act
    before it answers; an empty list with ``text`` means the model is done.
    """

    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str = "stop"
    model: str = ""
    usage: LLMUsage = Field(default_factory=LLMUsage)
    latency_ms: int = 0


class LLMProvider(ABC):
    """Abstract chat-completion provider with tool-calling support."""

    #: Short provider id, e.g. "anthropic" or "openai".
    provider_name: str = "base"

    @property
    @abstractmethod
    def model(self) -> str:
        """The concrete model id this provider will call."""

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> LLMResponse:
        """Send a conversation (and optional tool specs) and return one response.

        ``tools`` is the provider-appropriate spec list produced by the tool
        registry (``openai_specs()`` or ``anthropic_specs()``); each concrete
        provider is paired with the matching renderer by the factory.
        """
