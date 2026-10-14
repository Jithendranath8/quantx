"""
QuantX — Parsing a model's JSON decision.

Both the single-shot analyst and the orchestration synthesis step ask the model
for a strict JSON decision and parse it back into an :class:`AgentDecision`.
Keeping that in one place means the fence-stripping tolerance and the schema
binding never drift between the two paths.
"""

from __future__ import annotations

import json

from app.schemas.agent import AgentDecision


def strip_code_fences(text: str) -> str:
    """Remove a ```json … ``` fence a model sometimes wraps JSON in."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def parse_agent_decision(text: str) -> AgentDecision:
    """Parse model text into an :class:`AgentDecision`; raises on malformed input.

    Callers are expected to catch and degrade to WAIT, so parsing failures are
    surfaced rather than swallowed here.
    """
    return AgentDecision.model_validate(json.loads(strip_code_fences(text)))
