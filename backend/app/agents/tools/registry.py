"""
QuantX — Agent Tool Registry.

Holds the set of tools an agent may call and renders their specs in the three
dialects the rest of the system speaks:

  * ``openai_specs()``     → ``[{"type": "function", "function": {...}}]``
  * ``anthropic_specs()``  → ``[{"name", "description", "input_schema"}]``
  * ``mcp_tools()``        → ``[{"name", "description", "inputSchema"}]``

A single registry definition therefore drives the OpenAI-compatible loop, the
Anthropic loop, and the MCP server without the tool list drifting between them.
"""

from __future__ import annotations

from typing import Any

from app.agents.tools.base import Tool, ToolContext, ToolResult
from app.core.logging import get_logger

logger = get_logger(__name__)


class ToolRegistry:
    """An ordered, name-indexed collection of :class:`Tool` instances."""

    def __init__(self, tools: list[Tool[Any]] | None = None) -> None:
        self._tools: dict[str, Tool[Any]] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool[Any]) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool name: {tool.name!r}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool[Any] | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def all(self) -> list[Tool[Any]]:
        return list(self._tools.values())

    def subset(self, names: list[str]) -> ToolRegistry:
        """Return a new registry with only the named tools (preserving order).

        Used by the orchestration layer to give each specialist agent exactly
        the tools its role is allowed to touch.
        """
        missing = [n for n in names if n not in self._tools]
        if missing:
            raise KeyError(f"Unknown tools: {missing}")
        return ToolRegistry([self._tools[n] for n in names])

    async def invoke(self, name: str, arguments: dict[str, Any] | None, ctx: ToolContext) -> ToolResult:
        """Look up and run a tool by name, returning a structured error if unknown."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                ok=False,
                tool=name,
                error=f"Unknown tool {name!r}. Available: {', '.join(self._tools) or '(none)'}",
            )
        logger.info("tool_invoked", tool=name, mutating=tool.mutating)
        return await tool(arguments, ctx)

    # ── spec renderers ───────────────────────────────────────────────

    def openai_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.json_schema(),
                },
            }
            for t in self._tools.values()
        ]

    def anthropic_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.json_schema(),
            }
            for t in self._tools.values()
        ]

    def mcp_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.json_schema(),
            }
            for t in self._tools.values()
        ]
