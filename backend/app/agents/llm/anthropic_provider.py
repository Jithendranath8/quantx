"""
QuantX — Anthropic LLM provider (native tool use).

Translates the normalized :class:`~app.agents.llm.base.ChatMessage` stream to
the Anthropic Messages API and back. Two Anthropic-specific rules are handled
here so the loop never has to care:

* The system prompt is a top-level parameter, not a message, so system turns
  are lifted out and concatenated.
* ``tool_result`` blocks must live in the *user* turn immediately following the
  assistant ``tool_use``, and several results from one assistant turn must be
  grouped into a single user message — so consecutive tool turns are merged.
"""

from __future__ import annotations

import time
from typing import Any

from app.agents.llm.base import ChatMessage, LLMProvider, LLMResponse, LLMUsage, ToolCall
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

REQUEST_TIMEOUT_SECONDS = 90.0


class AnthropicProvider(LLMProvider):
    """Tool-calling provider over the Anthropic Messages API."""

    provider_name = "anthropic"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        # Imported lazily so the dependency is only required when this provider
        # is actually selected; OpenAI-only deployments need not install it.
        from anthropic import AsyncAnthropic

        settings = get_settings()
        self._model = model or settings.anthropic_model
        self._client = AsyncAnthropic(
            api_key=api_key if api_key is not None else settings.anthropic_api_key,
            timeout=REQUEST_TIMEOUT_SECONDS,
            max_retries=1,
        )

    @property
    def model(self) -> str:
        return self._model

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> LLMResponse:
        started = time.perf_counter()
        system_text, anthropic_messages = self._translate(messages)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": anthropic_messages,
        }
        if system_text:
            kwargs["system"] = system_text
        if tools:
            kwargs["tools"] = tools

        response = await self._client.messages.create(**kwargs)

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                args = block.input if isinstance(block.input, dict) else {}
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=args))

        usage = LLMUsage(
            input_tokens=getattr(response.usage, "input_tokens", 0) or 0,
            output_tokens=getattr(response.usage, "output_tokens", 0) or 0,
        )
        return LLMResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            finish_reason=response.stop_reason or "stop",
            model=response.model or self._model,
            usage=usage,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    @staticmethod
    def _translate(messages: list[ChatMessage]) -> tuple[str, list[dict[str, Any]]]:
        """Return (system_text, anthropic_messages) from the normalized stream."""
        system_parts: list[str] = []
        out: list[dict[str, Any]] = []

        for m in messages:
            if m.role == "system":
                if m.content:
                    system_parts.append(m.content)
                continue

            if m.role == "tool":
                block = {
                    "type": "tool_result",
                    "tool_use_id": m.tool_call_id,
                    "content": m.content,
                }
                # Merge into the preceding user turn when it is also tool results,
                # as the API requires grouped results from one assistant turn.
                if out and out[-1]["role"] == "user" and _is_tool_result_turn(out[-1]):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
                continue

            if m.role == "assistant":
                content: list[dict[str, Any]] = []
                if m.content:
                    content.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    content.append(
                        {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments}
                    )
                out.append({"role": "assistant", "content": content})
                continue

            # user
            out.append({"role": "user", "content": [{"type": "text", "text": m.content}]})

        return "\n\n".join(system_parts), out


def _is_tool_result_turn(message: dict[str, Any]) -> bool:
    content = message.get("content")
    return (
        isinstance(content, list)
        and len(content) > 0
        and all(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
    )
