"""
QuantX — OpenAI-compatible LLM provider (function calling).

Works against any endpoint speaking the OpenAI chat-completions API — OpenAI,
a local Ollama server, Groq, Gemini's OpenAI shim, OpenRouter — so the agent
runtime inherits the same provider freedom the single-shot agent already had,
now with tool calling on top.
"""

from __future__ import annotations

import json
import time
from typing import Any

from openai import AsyncOpenAI

from app.agents.llm.base import ChatMessage, LLMProvider, LLMResponse, LLMUsage, ToolCall
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"
REQUEST_TIMEOUT_SECONDS = 90.0


class OpenAIProvider(LLMProvider):
    """Tool-calling provider over the OpenAI chat-completions API."""

    provider_name = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        settings = get_settings()
        self._model = model or settings.openai_model
        self._client = AsyncOpenAI(
            api_key=(api_key if api_key is not None else settings.openai_api_key) or "not-required",
            base_url=(base_url if base_url is not None else settings.openai_base_url) or OPENAI_DEFAULT_BASE_URL,
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
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [self._to_openai_message(m) for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        tool_calls: list[ToolCall] = []
        for call in message.tool_calls or []:
            tool_calls.append(
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=_safe_json(call.function.arguments),
                )
            )

        usage = LLMUsage(
            input_tokens=getattr(response.usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(response.usage, "completion_tokens", 0) or 0,
        )
        return LLMResponse(
            text=message.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            model=response.model or self._model,
            usage=usage,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    @staticmethod
    def _to_openai_message(m: ChatMessage) -> dict[str, Any]:
        if m.role == "tool":
            return {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}
        if m.role == "assistant" and m.tool_calls:
            return {
                "role": "assistant",
                "content": m.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in m.tool_calls
                ],
            }
        return {"role": m.role, "content": m.content}


def _safe_json(raw: str | None) -> dict[str, Any]:
    """Parse a tool-call argument string; malformed JSON degrades to empty args.

    A model occasionally emits invalid JSON for arguments. Returning {} lets the
    tool's own validator produce a readable error the model can correct, rather
    than crashing the loop here.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        logger.warning("tool_call_arguments_not_json", raw=raw[:200])
        return {}
