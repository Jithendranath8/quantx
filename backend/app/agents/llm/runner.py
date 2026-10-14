"""
QuantX — Agentic tool-calling loop.

:class:`AgentRunner` is the heart of the agentic runtime. Given a system prompt,
a user task, a tool registry and an execution context, it runs the
observe → call tools → observe cycle until the model produces a final answer or
the iteration ceiling is hit:

    1. Ask the provider for a response, offering the registry's tools.
    2. If the model requested tools, execute each through the registry (which
       enforces validation and the mutation gate) and feed the results back.
    3. Repeat. Stop when the model answers with no tool calls.

The loop is provider-neutral: it renders tool specs in the dialect the selected
provider expects and speaks only the normalized message types. The iteration
ceiling (``agent_max_tool_iterations``) guarantees termination and bounds cost.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.agents.llm.base import ChatMessage, LLMProvider, ToolCall
from app.core.config import get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.agents.tools.base import ToolContext
    from app.agents.tools.registry import ToolRegistry

logger = get_logger(__name__)


class ToolInvocation(BaseModel):
    """A record of one tool call made during a run (for observability/audit)."""

    name: str
    arguments: dict[str, Any]
    ok: bool
    error: str | None = None
    latency_ms: int = 0


class AgentRunResult(BaseModel):
    """Everything a caller needs after a run: the answer and the full trace."""

    final_text: str
    provider: str
    model: str
    iterations: int
    tool_invocations: list[ToolInvocation] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    stopped_on_limit: bool = False
    transcript: list[ChatMessage] = Field(default_factory=list)


class AgentRunner:
    """Runs a bounded tool-calling loop for one agent over one task."""

    def __init__(
        self,
        provider: LLMProvider,
        registry: ToolRegistry,
        ctx: ToolContext,
        *,
        max_iterations: int | None = None,
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._ctx = ctx
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_iterations = max_iterations or get_settings().agent_max_tool_iterations

    def _tool_specs(self) -> list[dict[str, Any]]:
        """Render tools in the dialect the active provider understands."""
        if self._provider.provider_name == "anthropic":
            return self._registry.anthropic_specs()
        return self._registry.openai_specs()

    async def run(self, system_prompt: str, user_prompt: str) -> AgentRunResult:
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
        tools = self._tool_specs()
        invocations: list[ToolInvocation] = []
        input_tokens = 0
        output_tokens = 0

        for iteration in range(1, self._max_iterations + 1):
            response = await self._provider.chat(
                messages,
                tools=tools,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens

            if not response.tool_calls:
                messages.append(ChatMessage(role="assistant", content=response.text))
                return AgentRunResult(
                    final_text=response.text,
                    provider=self._provider.provider_name,
                    model=response.model,
                    iterations=iteration,
                    tool_invocations=invocations,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    transcript=messages,
                )

            # Record the assistant's tool-call turn, then execute each call.
            messages.append(
                ChatMessage(role="assistant", content=response.text, tool_calls=response.tool_calls)
            )
            for call in response.tool_calls:
                invocation, tool_message = await self._execute(call)
                invocations.append(invocation)
                messages.append(tool_message)

        # Iteration ceiling reached: ask once more for a final answer with no tools.
        logger.warning("agent_hit_iteration_ceiling", iterations=self._max_iterations)
        final = await self._provider.chat(
            [*messages, ChatMessage(role="user", content="Provide your final answer now without calling tools.")],
            tools=None,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        input_tokens += final.usage.input_tokens
        output_tokens += final.usage.output_tokens
        return AgentRunResult(
            final_text=final.text,
            provider=self._provider.provider_name,
            model=final.model,
            iterations=self._max_iterations,
            tool_invocations=invocations,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stopped_on_limit=True,
            transcript=messages,
        )

    async def _execute(self, call: ToolCall) -> tuple[ToolInvocation, ChatMessage]:
        """Run one tool call through the registry and build its tool message."""
        result = await self._registry.invoke(call.name, call.arguments, self._ctx)
        invocation = ToolInvocation(
            name=call.name,
            arguments=call.arguments,
            ok=result.ok,
            error=result.error,
            latency_ms=result.latency_ms,
        )
        tool_message = ChatMessage(
            role="tool",
            name=call.name,
            tool_call_id=call.id,
            content=result.to_model_text(),
        )
        return invocation, tool_message
