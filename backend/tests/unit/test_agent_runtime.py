"""
QuantX — Agentic LLM runtime tests.

Drives the tool-calling loop with a scripted provider so the observe → act →
observe cycle, the iteration ceiling, and the provider-dialect selection are
tested deterministically without any network call. Also covers the Anthropic
message translation, the OpenAI message mapping, and the provider factory.
"""

from typing import TYPE_CHECKING, Any, cast

import pytest
from pydantic import BaseModel

from app.agents.llm.anthropic_provider import AnthropicProvider
from app.agents.llm.base import ChatMessage, LLMProvider, LLMResponse, LLMUsage, ToolCall
from app.agents.llm.factory import build_provider
from app.agents.llm.openai_provider import OpenAIProvider
from app.agents.llm.runner import AgentRunner
from app.agents.tools.base import Tool, ToolContext, ToolResult
from app.agents.tools.registry import ToolRegistry
from app.core.config import Settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# ── test doubles ─────────────────────────────────────────────────────


class _EchoArgs(BaseModel):
    text: str


class EchoTool(Tool[_EchoArgs]):
    name = "echo"
    description = "Echo the given text back."
    args_model = _EchoArgs

    async def _run(self, args: _EchoArgs, ctx: ToolContext) -> ToolResult:
        return self._ok({"echo": args.text})


class ScriptedProvider(LLMProvider):
    """Returns queued responses; an empty queue yields a forced final answer.

    Records the ``tools`` argument of every ``chat`` call so tests can assert
    which spec dialect the runner rendered.
    """

    def __init__(self, responses: list[LLMResponse], provider_name: str = "openai") -> None:
        self._responses = list(responses)
        self.provider_name = provider_name
        self.captured_tools: list[Any] = []

    @property
    def model(self) -> str:
        return "scripted"

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> LLMResponse:
        self.captured_tools.append(tools)
        # The runner's final no-tools call always sets tools=None; honor it as a
        # request for a plain final answer regardless of what remains queued.
        if tools is None or not self._responses:
            return LLMResponse(text="forced final", model="scripted", usage=LLMUsage())
        return self._responses.pop(0)


def _ctx() -> ToolContext:
    # The echo tool never touches the session, so a placeholder is fine here.
    return ToolContext(session=cast("AsyncSession", None))


def _registry() -> ToolRegistry:
    return ToolRegistry([EchoTool()])


# ── the loop ─────────────────────────────────────────────────────────


async def test_loop_executes_tool_then_answers() -> None:
    provider = ScriptedProvider(
        [
            LLMResponse(tool_calls=[ToolCall(id="c1", name="echo", arguments={"text": "hi"})]),
            LLMResponse(text="All done.", usage=LLMUsage(input_tokens=10, output_tokens=5)),
        ]
    )
    runner = AgentRunner(provider, _registry(), _ctx())
    result = await runner.run("system", "please echo")

    assert result.final_text == "All done."
    assert result.iterations == 2
    assert result.stopped_on_limit is False
    assert len(result.tool_invocations) == 1
    assert result.tool_invocations[0].name == "echo"
    assert result.tool_invocations[0].ok is True
    # the tool result was fed back as a tool message
    assert any(m.role == "tool" and "echo" in (m.content or "") for m in result.transcript)


async def test_loop_handles_unknown_tool_without_crashing() -> None:
    provider = ScriptedProvider(
        [
            LLMResponse(tool_calls=[ToolCall(id="c1", name="nope", arguments={})]),
            LLMResponse(text="recovered"),
        ]
    )
    runner = AgentRunner(provider, _registry(), _ctx())
    result = await runner.run("system", "task")

    assert result.final_text == "recovered"
    assert result.tool_invocations[0].ok is False
    assert "Unknown tool" in (result.tool_invocations[0].error or "")


async def test_loop_stops_on_iteration_ceiling() -> None:
    # Always request a tool: the queue is longer than the ceiling.
    always_tool = [
        LLMResponse(tool_calls=[ToolCall(id=f"c{i}", name="echo", arguments={"text": "x"})])
        for i in range(20)
    ]
    provider = ScriptedProvider(always_tool)
    runner = AgentRunner(provider, _registry(), _ctx(), max_iterations=3)
    result = await runner.run("system", "task")

    assert result.stopped_on_limit is True
    assert result.iterations == 3
    assert result.final_text == "forced final"
    # the final call was made with no tools offered
    assert provider.captured_tools[-1] is None


async def test_runner_renders_anthropic_specs_for_anthropic_provider() -> None:
    provider = ScriptedProvider([LLMResponse(text="done")], provider_name="anthropic")
    runner = AgentRunner(provider, _registry(), _ctx())
    await runner.run("system", "task")

    first_tools = provider.captured_tools[0]
    assert first_tools is not None
    # anthropic dialect uses "input_schema"; openai uses "parameters"
    assert "input_schema" in first_tools[0]
    assert "type" not in first_tools[0]


async def test_runner_renders_openai_specs_for_openai_provider() -> None:
    provider = ScriptedProvider([LLMResponse(text="done")], provider_name="openai")
    runner = AgentRunner(provider, _registry(), _ctx())
    await runner.run("system", "task")

    first_tools = provider.captured_tools[0]
    assert first_tools is not None
    assert first_tools[0]["type"] == "function"


# ── provider translation / mapping ───────────────────────────────────


def test_anthropic_translate_lifts_system_and_merges_tool_results() -> None:
    messages = [
        ChatMessage(role="system", content="you are a quant"),
        ChatMessage(role="user", content="analyze"),
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(id="a", name="t1", arguments={}),
                ToolCall(id="b", name="t2", arguments={}),
            ],
        ),
        ChatMessage(role="tool", tool_call_id="a", content="r1"),
        ChatMessage(role="tool", tool_call_id="b", content="r2"),
    ]
    system_text, out = AnthropicProvider._translate(messages)

    assert system_text == "you are a quant"
    # user, assistant(tool_use x2), user(tool_result x2 merged)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert len(out[-1]["content"]) == 2
    assert all(b["type"] == "tool_result" for b in out[-1]["content"])


def test_openai_message_mapping_for_tool_and_assistant_calls() -> None:
    assistant = ChatMessage(
        role="assistant", content="thinking", tool_calls=[ToolCall(id="x", name="echo", arguments={"text": "hi"})]
    )
    mapped = OpenAIProvider._to_openai_message(assistant)
    assert mapped["role"] == "assistant"
    assert mapped["tool_calls"][0]["function"]["name"] == "echo"

    tool_msg = ChatMessage(role="tool", tool_call_id="x", content="result")
    mapped_tool = OpenAIProvider._to_openai_message(tool_msg)
    assert mapped_tool == {"role": "tool", "tool_call_id": "x", "content": "result"}


# ── factory & config ─────────────────────────────────────────────────


def test_factory_builds_openai_provider() -> None:
    provider = build_provider("openai")
    assert isinstance(provider, OpenAIProvider)


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        build_provider("bogus")


def test_resolved_provider_prefers_anthropic_when_key_present() -> None:
    s = Settings(llm_provider="auto", anthropic_api_key="sk-ant", openai_api_key="", openai_base_url=None)
    assert s.resolved_llm_provider == "anthropic"


def test_resolved_provider_falls_back_to_openai_without_anthropic_key() -> None:
    s = Settings(llm_provider="auto", anthropic_api_key="", openai_base_url="http://localhost:11434/v1")
    assert s.resolved_llm_provider == "openai"


def test_resolved_provider_respects_explicit_choice() -> None:
    s = Settings(llm_provider="openai", anthropic_api_key="sk-ant")
    assert s.resolved_llm_provider == "openai"
