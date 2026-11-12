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
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ValidationError

from app.core.exceptions import QuantXError
from app.core.logging import get_logger

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.connectors.binance_client import BinanceClient

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
    # Second gate, for the few tools that act on the exchange itself.
    allow_exchange_actions: bool = False
    # Free-form scratch space for an orchestration run (e.g. cached context).
    scratch: dict[str, Any] = field(default_factory=dict)


async def _end_transaction(ctx: ToolContext, rollback: bool = False) -> None:
    """Finish the session's current transaction, releasing its connection."""
    try:
        if rollback:
            await ctx.session.rollback()
        else:
            await ctx.session.commit()
    except Exception as exc:
        logger.warning("tool_transaction_release_failed", error=str(exc))


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


class Tool[ArgsT: BaseModel](ABC):
    """Base class for an agent tool, generic over its argument model.

    Subclasses parameterize the generic with their Pydantic argument model —
    ``class GetPriceTool(Tool[_SymbolArgs])`` — declare ``name``, ``description``
    and ``args_model``, then implement :meth:`_run`. Making the base generic
    keeps :meth:`_run` type-safe per tool (no Liskov violation from narrowing
    the argument type). Argument validation, timing and error capture are
    handled here, so every tool inherits identical safety behaviour.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    #: The Pydantic model raw arguments are validated against.
    args_model: type[ArgsT]
    #: True when the tool can change persistent or exchange state.
    mutating: ClassVar[bool] = False
    #: True when the tool sends signed requests to the exchange. These need
    #: their own permission on top of ``allow_mutations``: "may place paper
    #: orders" must not silently also mean "may cancel real exchange orders".
    exchange_action: ClassVar[bool] = False

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

        if self.exchange_action and not ctx.allow_exchange_actions:
            return self._err(
                "This tool acts on the exchange and is not enabled for this agent. "
                "Nothing was halted or cancelled.",
                started,
            )

        try:
            args = self.args_model.model_validate(raw_arguments)
        except ValidationError as exc:
            return self._err(f"Invalid arguments: {exc.errors(include_url=False)}", started)

        try:
            result = await self._run(args, ctx)
        except Exception as exc:
            logger.error("tool_execution_failed", tool=self.name, error=str(exc))
            # A failed statement poisons the transaction for every later tool
            # in the run; roll it back so the next call starts clean.
            await _end_transaction(ctx, rollback=True)
            # Domain errors carry a message written for callers. Anything else
            # is reported by kind only: raw exception text can carry hostnames,
            # SQL and upstream response bodies, and the model's output is
            # returned to the user.
            if isinstance(exc, QuantXError):
                return self._err(f"{type(exc).__name__}: {exc.message}", started)
            return self._err(f"{type(exc).__name__}: the tool could not complete this call", started)

        # Hand the pooled connection back between tool calls. The model is
        # consulted after each one, and a connection held idle across those
        # waits is a connection no other request can use.
        await _end_transaction(ctx)
        result.latency_ms = int((time.perf_counter() - started) * 1000)
        return result

    @abstractmethod
    async def _run(self, args: ArgsT, ctx: ToolContext) -> ToolResult:
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
