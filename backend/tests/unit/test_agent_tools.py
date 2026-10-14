"""
QuantX — Agent tool-layer tests.

Covers the safety invariants (argument validation, the mutation gate), the
spec renderers used by the OpenAI / Anthropic / MCP surfaces, and that each
read-only tool wraps its underlying service against real stored data.
"""

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools import build_default_registry
from app.agents.tools.base import ToolContext
from app.agents.tools.registry import ToolRegistry
from app.connectors.binance_client import BinanceClient
from app.models.user import User
from tests.conftest import FakeBinanceClient
# asyncio_mode=auto (pyproject) runs async tests without an explicit mark.


def _fake_client() -> BinanceClient:
    return cast(BinanceClient, FakeBinanceClient())


def _registry() -> ToolRegistry:
    return build_default_registry()


def test_registry_renders_all_dialects() -> None:
    reg = _registry()
    names = set(reg.names())
    assert {"get_price", "get_klines", "get_indicators", "run_backtest", "validate_trade"} <= names

    openai = reg.openai_specs()
    anthropic = reg.anthropic_specs()
    mcp = reg.mcp_tools()
    assert len(openai) == len(anthropic) == len(mcp) == len(names)
    assert all(s["type"] == "function" and "parameters" in s["function"] for s in openai)
    assert all("input_schema" in s for s in anthropic)
    assert all("inputSchema" in s for s in mcp)


def test_subset_selects_named_tools() -> None:
    reg = _registry().subset(["get_price", "get_indicators"])
    assert reg.names() == ["get_price", "get_indicators"]


def test_subset_rejects_unknown() -> None:
    with pytest.raises(KeyError):
        _registry().subset(["nope"])


async def test_invalid_arguments_return_structured_error(db_session: AsyncSession) -> None:
    reg = _registry()
    ctx = ToolContext(session=db_session, client=FakeBinanceClient())
    # symbol too short -> validation error, not an exception
    result = await reg.invoke("get_price", {"symbol": "X"}, ctx)
    assert result.ok is False
    assert "Invalid arguments" in (result.error or "")


async def test_unknown_tool_is_reported(db_session: AsyncSession) -> None:
    result = await _registry().invoke("does_not_exist", {}, ToolContext(session=db_session))
    assert result.ok is False
    assert "Unknown tool" in (result.error or "")


async def test_mutation_gate_blocks_orders_by_default(db_session: AsyncSession, test_user: User) -> None:
    reg = _registry()
    ctx = ToolContext(session=db_session, user_id=test_user.id, client=_fake_client())
    assert ctx.allow_mutations is False
    result = await reg.invoke(
        "submit_paper_order", {"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.1}, ctx
    )
    assert result.ok is False
    assert "read-only" in (result.error or "").lower()


async def test_get_price_uses_exchange_client(db_session: AsyncSession) -> None:
    ctx = ToolContext(session=db_session, client=cast(BinanceClient, FakeBinanceClient(price=50_000.0)))
    result = await _registry().invoke("get_price", {"symbol": "BTCUSDT"}, ctx)
    assert result.ok is True
    assert isinstance(result.data, dict)
    assert result.data["price"] == 50_000.0


async def test_get_klines_reads_stored_candles(db_session: AsyncSession, seeded_candles: int) -> None:
    ctx = ToolContext(session=db_session)
    result = await _registry().invoke(
        "get_klines", {"symbol": "BTCUSDT", "timeframe": "1h", "limit": 30}, ctx
    )
    assert result.ok is True
    assert isinstance(result.data, dict)
    assert len(result.data["candles"]) == 30
    # chronological order
    ts = [c["timestamp"] for c in result.data["candles"]]
    assert ts == sorted(ts)


async def test_get_indicators_snapshot(db_session: AsyncSession, seeded_candles: int) -> None:
    ctx = ToolContext(session=db_session)
    result = await _registry().invoke(
        "get_indicators", {"symbol": "BTCUSDT", "timeframes": ["1h"]}, ctx
    )
    assert result.ok is True
    assert isinstance(result.data, dict)
    assert "1h" in result.data["indicators"]


async def test_run_backtest_returns_metrics(db_session: AsyncSession, seeded_candles: int) -> None:
    ctx = ToolContext(session=db_session)
    result = await _registry().invoke(
        "run_backtest",
        {"symbol": "BTCUSDT", "timeframe": "1h", "strategy_name": "ema_crossover"},
        ctx,
    )
    assert result.ok is True
    assert isinstance(result.data, dict)
    assert "metrics" in result.data
    assert "sharpe_ratio" in result.data["metrics"]


async def test_validate_trade_runs_risk_engine(db_session: AsyncSession, test_user: User) -> None:
    ctx = ToolContext(session=db_session, user_id=test_user.id, account_balance=100_000.0)
    result = await _registry().invoke(
        "validate_trade",
        {
            "symbol": "BTCUSDT",
            "action": "BUY",
            "order_amount_usd": 1_000.0,
            "entry_price": 50_000.0,
            "stop_loss_price": 49_000.0,
        },
        ctx,
    )
    assert result.ok is True
    assert isinstance(result.data, dict)
    assert "is_approved" in result.data
    assert "recommended_position_size_usd" in result.data
