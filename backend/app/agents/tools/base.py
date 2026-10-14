"""
QuantX — Agent Tool Layer: base abstractions.

A *tool* is a typed, schema-described capability an LLM agent may invoke. Each
tool wraps an existing QuantX service (indicators, backtesting, risk, paper
trading, …) behind a validated argument model and a uniform result envelope, so
the same tool can be driven by:

  * the OpenAI-compatible function-calling loop,
  * Anthropic native tool use,
  * the Model Context Protocol (MCP) server, and
  * the LangGraph orchestration layer.

Two invariants make this safe to hand to a model:

1. **Validation at the edge.** Raw ``arguments`` from the model are parsed
   through a Pydantic ``args_model`` before any service is touched. A malformed
   tool call becomes a structured error the model can read and retry, never an
   exception that aborts the loop.

2. **Mutation is opt-in and still gated downstream.** A tool that changes state
   (submits an order, trips the kill switch) sets ``mutating = True``. The
   :class:`ToolContext` carries ``allow_mutations`` — default *False* — so an
   analysis-only agent physically cannot place an order. Even when mutations are
   allowed, execution tools still pass through the deterministic risk engine and
   the mainnet interlock. The LLM gets tools, never direct control of money.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError

from app.connectors.binance_client import BinanceClient
from app.core.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


@dataclass
class ToolContext:
    """Execution context threaded into every tool call.

    The context — not the model — owns identity, the DB session, and the
    permission to mutate state. The model only ever supplies ``arguments``.
    """

    session: AsyncSession
    user_id: uuid.UUID | None = None
    client: BinanceClient | None = None
    account_balance: float = 100_000.0
    # Hard gate: mutating tools refuse to run unless this is explicitly True.
    allow_mutations: bool = False
    # Free-form scratch space for an orchestration run (e.g. cached context).
    scratch: dict[str, Any] = field(default_factory=dict)


class ToolResult(BaseModel):
    """Uniform envelope returned by every tool.

    ``ok`` separates "the tool ran and here is data" from "the tool could not
    run and here is why", without raising. The model reads ``error`` and adapts.
    """

    ok: bool
    tool: str
    data: dict[str, Any] | list[Any] | None = None
    error: str | None = None
    latency_ms: int = 0

    def to_model_text(self) -> str:
        """Render the result as the compact JSON string handed back to the LLM."""
        import json

        if self.ok:
            payload: dict[str, Any] = {"ok": True, "data": self.data}
        else:
            payload = {"ok": False, "error": self.error}
        return json.dumps(payload, default=str, separators=(",", ":"))


class Tool(ABC):
    """Base class for an agent tool.

    Subclasses declare ``name``, ``description`` and an ``args_model`` (a
    Pydantic model describing the accepted arguments), then implement
    :meth:`_run`. Argument validation, timing and error capture are handled here.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    args_model: ClassVar[type[BaseModel]]
    #: True when the tool can change persistent or exchange state.
    mutating: ClassVar[bool] = False

    def json_schema(self) -> dict[str, Any]:
        """JSON Schema for this tool's arguments (provider-neutral)."""
        schema = self.args_model.model_json_schema()
        # Providers reject ``$defs``-only bare refs at the top level; the models
        # here are flat, so the generated schema is already an object schema.
        schema.pop("title", None)
        return schema

    async def __call__(self, raw_arguments: dict[str, Any] | None, ctx: ToolContext) -> ToolResult:
        """Validate arguments, enforce the mutation gate, and dispatch to :meth:`_run`."""
        started = time.perf_counter()
        raw_arguments = raw_arguments or {}

        if self.mutating and not ctx.allow_mutations:
            return self._err(
                "This tool mutates state and is disabled in the current (read-only) "
                "agent mode. No order or state change was attempted.",
                started,
            )

        try:
            args = self.args_model.model_validate(raw_arguments)
        except ValidationError as exc:
            return self._err(f"Invalid arguments: {exc.errors(include_url=False)}", started)

        try:
            result = await self._run(args, ctx)
        except Exception as exc:  # noqa: BLE001 — a tool must never abort the agent loop
            logger.error("tool_execution_failed", tool=self.name, error=str(exc))
            return self._err(f"{type(exc).__name__}: {exc}", started)

        result.latency_ms = int((time.perf_counter() - started) * 1000)
        return result

    @abstractmethod
    async def _run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        """Execute the tool. ``args`` is the validated ``args_model`` instance."""

    # ── helpers for subclasses ───────────────────────────────────────

    def _ok(self, data: dict[str, Any] | list[Any]) -> ToolResult:
        return ToolResult(ok=True, tool=self.name, data=data)

    def _err(self, message: str, started: float | None = None) -> ToolResult:
        latency = int((time.perf_counter() - started) * 1000) if started else 0
        return ToolResult(ok=False, tool=self.name, error=message, latency_ms=latency)

    def _require_user(self, ctx: ToolContext) -> uuid.UUID:
        if ctx.user_id is None:
            raise PermissionError("This tool requires an authenticated user in context.")
        return ctx.user_id
