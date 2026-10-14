"""
QuantX — Orchestration state.

The shared state passed between nodes of the multi-agent graph. Each specialist
appends its :class:`SpecialistReport`; the synthesis node reads them all to form
the final decision. Using a Pydantic model (rather than a bare dict) keeps the
state typed and self-documenting as it flows through LangGraph.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SpecialistReport(BaseModel):
    """One specialist agent's contribution to a run."""

    agent: str
    summary: str = ""
    tool_calls: int = 0
    data: dict[str, Any] = Field(default_factory=dict)


class OrchestrationState(BaseModel):
    """State threaded through the orchestration graph."""

    symbol: str
    account_balance: float = 100_000.0
    # Numeric spot price captured up front so the deterministic validator always
    # has a reference, independent of what the LLM narrates.
    market_price: float | None = None
    reports: dict[str, SpecialistReport] = Field(default_factory=dict)
    halted: bool = False
    final_decision: dict[str, Any] | None = None
    executed_order: dict[str, Any] | None = None
    log: list[str] = Field(default_factory=list)
