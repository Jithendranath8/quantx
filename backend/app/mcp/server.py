"""
QuantX — Model Context Protocol server.

Serves the QuantX tool registry over MCP (stdio), so Claude Code and other MCP
clients can drive the platform: read prices/indicators, run backtests, query the
risk engine, get an ML prediction, and — only when explicitly enabled — place
paper orders.

Identity and permissions are bound from the environment at start-up, never from
the client:

  QUANTX_MCP_USER_ID           bind calls to this user (UUID) for user-scoped tools
  QUANTX_MCP_ALLOW_MUTATIONS   "true" to permit paper-order / kill-switch tools
  QUANTX_MCP_ACCOUNT_BALANCE   balance assumed for risk sizing (default 100000)

Run it (after `pip install -e '.[mcp]'`):
  python -m app.mcp.server
Register in a client's MCP config as command `python` args `["-m","app.mcp.server"]`.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import TYPE_CHECKING, Any

from app.agents.tools import build_default_registry
from app.agents.tools.base import ToolContext
from app.core.logging import get_logger
from app.mcp.handlers import handle_call, list_tool_specs

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = get_logger(__name__)

SERVER_NAME = "quantx"


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


async def _context_factory() -> tuple[ToolContext, Callable[[], Awaitable[None]]]:
    """Build a per-call ToolContext from environment-bound settings."""
    from app.connectors.binance_client import get_binance_client
    from app.core.database import get_session_factory

    session = get_session_factory()()

    user_id: uuid.UUID | None = None
    raw_user = os.getenv("QUANTX_MCP_USER_ID", "").strip()
    if raw_user:
        try:
            user_id = uuid.UUID(raw_user)
        except ValueError:
            logger.warning("mcp_invalid_user_id", value=raw_user)

    balance = float(os.getenv("QUANTX_MCP_ACCOUNT_BALANCE", "100000") or 100000)
    ctx = ToolContext(
        session=session,
        user_id=user_id,
        client=get_binance_client(),
        account_balance=balance,
        allow_mutations=_env_flag("QUANTX_MCP_ALLOW_MUTATIONS"),
    )

    async def _close() -> None:
        await session.close()

    return ctx, _close


def build_server() -> Any:  # pragma: no cover - requires the optional 'mcp' package
    """Construct the MCP Server with list_tools / call_tool handlers bound."""
    from mcp.types import TextContent, Tool

    from mcp.server import Server

    registry = build_default_registry()
    server = Server(SERVER_NAME)

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(name=spec["name"], description=spec["description"], inputSchema=spec["inputSchema"])
            for spec in list_tool_specs(registry)
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
        result = await handle_call(registry, _context_factory, name, arguments)
        return [TextContent(type="text", text=json.dumps(result, default=str))]

    return server


async def main() -> None:  # pragma: no cover - integration entrypoint
    """Run the server over stdio."""
    from mcp.server.stdio import stdio_server

    server = build_server()
    logger.info("mcp_server_starting", name=SERVER_NAME, mutations=_env_flag("QUANTX_MCP_ALLOW_MUTATIONS"))
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    asyncio.run(main())
