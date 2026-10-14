"""
QuantX — Specialist agent definitions.

Each specialist is a role: a focused system prompt plus the subset of tools that
role is permitted to use. Narrowing tools per role is both a safety measure (the
market analyst cannot place orders) and a quality one (a smaller, relevant tool
set yields more reliable tool choices from the model).

These are declarative specs; :mod:`app.agents.orchestration.graph` turns each
into a graph node backed by the shared :class:`~app.agents.llm.runner.AgentRunner`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.tools import EXECUTION_TOOLS, MARKET_TOOLS, RESEARCH_TOOLS, RISK_TOOLS


@dataclass(frozen=True)
class SpecialistSpec:
    """A specialist agent's role, tools, and task framing."""

    key: str
    title: str
    system_prompt: str
    tool_names: list[str]
    task_template: str

    def task(self, symbol: str) -> str:
        return self.task_template.format(symbol=symbol)


MARKET_ANALYST = SpecialistSpec(
    key="market",
    title="Market Data Analyst",
    system_prompt=(
        "You are a market-data analyst. Use the tools to read the live price and recent "
        "candles, then summarize price action, momentum and notable levels in 3-4 sentences. "
        "State only what the data supports. Do not invent news or figures."
    ),
    tool_names=MARKET_TOOLS,
    task_template="Summarize the current market state for {symbol} from live price and recent candles.",
)

TECHNICAL_ANALYST = SpecialistSpec(
    key="technical",
    title="Technical Analyst",
    system_prompt=(
        "You are a technical analyst. Use the indicator tools to read a multi-timeframe "
        "snapshot (trend, momentum, volatility) and summarize the technical posture and any "
        "confluence or conflict across timeframes in 3-4 sentences."
    ),
    tool_names=["get_indicators", "get_klines"],
    task_template="Assess the multi-timeframe technical posture for {symbol}.",
)

QUANT_ANALYST = SpecialistSpec(
    key="quant",
    title="Quant Strategy Analyst",
    system_prompt=(
        "You are a quantitative analyst. Use the strategy and backtest tools (and the ML "
        "prediction tool when available) to judge which approach has historical support for "
        "this symbol and what it implies now. Report measured results, not assumptions."
    ),
    tool_names=RESEARCH_TOOLS,
    task_template="Evaluate strategy/quant signals for {symbol} using backtests and any ML prediction.",
)

RISK_OFFICER = SpecialistSpec(
    key="risk",
    title="Risk Officer",
    system_prompt=(
        "You are a risk officer. Read the persisted risk state and validate a representative "
        "trade against the risk engine. Report whether trading is halted, the circuit-breaker "
        "state, and any binding limits. You cannot relax limits; only report them."
    ),
    tool_names=RISK_TOOLS,
    task_template="Report the risk posture for trading {symbol}: halt status and binding limits.",
)

# Ordered pipeline the supervisor walks by default.
PIPELINE: list[SpecialistSpec] = [MARKET_ANALYST, TECHNICAL_ANALYST, QUANT_ANALYST, RISK_OFFICER]

# Tools the (optional) execution step may use. Not given to any analyst.
EXECUTION_TOOL_NAMES = EXECUTION_TOOLS
