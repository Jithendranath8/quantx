"""
QuantX — MCP handler tests.

Cover the framework-free core (``app.mcp.handlers``): the tool-spec listing in
MCP shape, successful delegation to the registry, unknown-tool reporting, and
that the mutation gate still holds when a tool is reached via MCP. No ``mcp``
package is required to run these.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools import build_default_registry
from app.agents.tools.base import ToolContext
from app.connectors.binance_client import BinanceClient
from app.mcp.handlers import handle_call, list_tool_specs
from app.models.user import User
from tests.conftest import FakeBinanceClient


def _factory(
    db_session: AsyncSession, *, user: User | None = None, allow_mutations: bool = False
) -> Callable[[], Awaitable[tuple[ToolContext, Callable[[], Awaitable[None]]]]]:
    async def factory() -> tuple[ToolContext, Callable[[], Awaitable[None]]]:
        ctx = ToolContext(
            session=db_session,
            user_id=user.id if user else None,
            client=cast(BinanceClient, FakeBinanceClient(price=50_000.0)),
            allow_mutations=allow_mutations,
        )

        async def _close() -> None:
            return None

        return ctx, _close

    return factory


def test_list_tool_specs_mcp_shape() -> None:
    specs = list_tool_specs(build_default_registry())
    names = {s["name"] for s in specs}
    assert {"get_price", "predict_direction", "run_backtest", "validate_trade"} <= names
    assert all("inputSchema" in s and "description" in s for s in specs)


async def test_handle_call_success(db_session: AsyncSession) -> None:
    registry = build_default_registry()
    result = await handle_call(registry, _factory(db_session), "get_price", {"symbol": "BTCUSDT"})
    assert result["ok"] is True
    assert result["data"]["price"] == 50_000.0


async def test_handle_call_unknown_tool(db_session: AsyncSession) -> None:
    registry = build_default_registry()
    result = await handle_call(registry, _factory(db_session), "nope", {})
    assert result["ok"] is False
    assert "Unknown tool" in result["error"]


async def test_handle_call_respects_mutation_gate(db_session: AsyncSession, test_user: User) -> None:
    registry = build_default_registry()
    result = await handle_call(
        registry,
        _factory(db_session, user=test_user, allow_mutations=False),
        "submit_paper_order",
        {"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.1},
    )
    assert result["ok"] is False
    assert "read-only" in result["error"].lower()
