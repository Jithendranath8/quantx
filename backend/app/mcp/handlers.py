"""
QuantX — MCP request handlers (framework-free core).

The Model Context Protocol server exposes the QuantX tool registry to any MCP
client (Claude Code, Claude Desktop, …). The protocol wiring lives in
``server.py``; the *logic* lives here and depends only on the tool registry, so
it is fully testable without the ``mcp`` package installed.

A handler builds a fresh :class:`ToolContext` per call via an injected factory —
the server binds identity and the mutation permission from environment at
start-up, so a remote MCP client can never escalate its own privileges.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from app.agents.tools.base import ToolContext

if TYPE_CHECKING:
    from app.agents.tools.registry import ToolRegistry

CtxFactory = Callable[[], Awaitable[tuple[ToolContext, Callable[[], Awaitable[None]]]]]


def list_tool_specs(registry: ToolRegistry) -> list[dict[str, Any]]:
    """Return the registry's tools in MCP ``inputSchema`` form."""
    return registry.mcp_tools()


async def handle_call(
    registry: ToolRegistry,
    ctx_factory: CtxFactory,
    name: str,
    arguments: dict[str, Any] | None,
) -> dict[str, Any]:
    """Execute one tool call and return a JSON-serializable result envelope.

    The context factory yields a context and a closer (to release the DB
    session), so each call is isolated and nothing leaks between clients.
    """
    ctx, close = await ctx_factory()
    try:
        result = await registry.invoke(name, arguments or {}, ctx)
        return {"ok": result.ok, "tool": result.tool, "data": result.data, "error": result.error}
    finally:
        await close()
