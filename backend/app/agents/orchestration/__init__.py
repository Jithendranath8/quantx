"""
QuantX — Multi-agent orchestration.

A LangGraph graph of specialist agents (market, technical, quant, risk) feeding
a synthesis step that emits one deterministically-validated decision, with an
optional paper-execution step gated on mutations being enabled.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.orchestration.graph import QuantXOrchestrator
from app.agents.orchestration.state import OrchestrationState, SpecialistReport
from app.agents.tools import build_default_registry

if TYPE_CHECKING:
    from app.agents.llm.base import LLMProvider
    from app.agents.tools.base import ToolContext
    from app.agents.tools.registry import ToolRegistry


def build_orchestrator(
    provider: LLMProvider,
    ctx: ToolContext,
    registry: ToolRegistry | None = None,
) -> QuantXOrchestrator:
    """Construct an orchestrator over the default toolset (or a supplied one)."""
    return QuantXOrchestrator(provider, registry or build_default_registry(), ctx)


__all__ = [
    "OrchestrationState",
    "QuantXOrchestrator",
    "SpecialistReport",
    "build_orchestrator",
]
