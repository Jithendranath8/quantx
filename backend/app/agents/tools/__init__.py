"""
QuantX — Agent Tool Layer.

A provider-neutral catalogue of capabilities an LLM agent may invoke, each
wrapping an existing QuantX service behind validated arguments and a uniform
result envelope. See :mod:`app.agents.tools.base` for the safety invariants.

``build_default_registry()`` returns the full toolset; the orchestration layer
narrows it per specialist agent with :meth:`ToolRegistry.subset`.
"""

from __future__ import annotations

from app.agents.tools.backtest_tools import ListStrategiesTool, RunBacktestTool
from app.agents.tools.base import Tool, ToolContext, ToolResult
from app.agents.tools.market_tools import GetIndicatorsTool, GetKlinesTool, GetPriceTool
from app.agents.tools.registry import ToolRegistry
from app.agents.tools.risk_tools import GetRiskStateTool, ValidateTradeTool
from app.agents.tools.trading_tools import (
    ActivateKillSwitchTool,
    GetPositionsTool,
    SubmitPaperOrderTool,
)

# Tool-group name constants so orchestration/MCP can reference roles without
# hard-coding string lists in several places.
MARKET_TOOLS = ["get_price", "get_klines", "get_indicators"]
RESEARCH_TOOLS = ["list_strategies", "run_backtest"]
RISK_TOOLS = ["validate_trade", "get_risk_state"]
EXECUTION_TOOLS = ["get_positions", "submit_paper_order", "activate_kill_switch"]


def build_default_registry() -> ToolRegistry:
    """Assemble the full set of tools available to QuantX agents."""
    return ToolRegistry(
        [
            # Market data & technical analysis
            GetPriceTool(),
            GetKlinesTool(),
            GetIndicatorsTool(),
            # Strategies & backtesting
            ListStrategiesTool(),
            RunBacktestTool(),
            # Risk
            ValidateTradeTool(),
            GetRiskStateTool(),
            # Paper execution & safety (mutating tools gated by allow_mutations)
            GetPositionsTool(),
            SubmitPaperOrderTool(),
            ActivateKillSwitchTool(),
        ]
    )


__all__ = [
    "Tool",
    "ToolContext",
    "ToolResult",
    "ToolRegistry",
    "build_default_registry",
    "MARKET_TOOLS",
    "RESEARCH_TOOLS",
    "RISK_TOOLS",
    "EXECUTION_TOOLS",
]
