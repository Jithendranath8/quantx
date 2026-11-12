# CLAUDE.md — QuantX

Guidance for Claude Code working in this repo. Read `project_state.md` for the
authoritative "what is / isn't implemented" list.

## What this is
QuantX is a FastAPI + React quantitative trading platform **with an agentic AI
layer**: multi-agent, tool-calling LLM orchestration on top of the platform's
own services, plus an ML price-direction model and an MCP server.

## Safety invariants (never weaken these)
1. **Mainnet interlock.** Real orders require BOTH `BINANCE_TESTNET=false` AND
   `ALLOW_MAINNET_TRADING=true`. Two independent flags. Never collapse to one.
2. **The LLM gets tools, never control of money.** Live trading is NOT exposed
   as an agent tool or over MCP. Agents can place *paper* orders only, and only
   when mutations are explicitly enabled.
3. **Deterministic gates are final.** `AIDecisionValidator` re-checks every
   agent decision against backend arithmetic; `RiskManager` is pure and
   non-overridable. A model can propose; math and explicit flags decide.

## Security rules (from the 2026-11-12 audit — keep every one)
The audit found 14 vulnerabilities; all came from breaking one of these. Each
has a regression test in `tests/integration/test_security_regressions.py` or a
guard in `tests/unit/test_route_security_inventory.py`. A failing guard means a
rule was broken: fix the code, not the test.

4. **Every route needs a signed-in user**, unless it is on the explicit public
   list in the route inventory test. Use `CurrentUser`; never trust a bare JWT.
5. **Live trading needs `LiveTrader`** (`users.can_trade_live`). All users share
   the operator's one exchange account and sign-up is open. Nothing in the API
   may set that flag. Any exchange action must be scoped to the caller's own
   orders by client order id, never by symbol.
6. **The server decides risk inputs.** Never size or check an order with a
   number the caller sent when the server can read it (price, balance,
   exposure). Working orders count toward limits, not just fills.
7. **Never retry an order submit.** Sent once; an unknown outcome is resolved
   by client order id. A 4xx from the exchange is final (`BinanceRejectedError`).
8. **Never hold a DB transaction across a network call** (exchange, LLM,
   broker). Commit first. Ten held connections stall a whole worker.
9. **Bound every input**: use `app/schemas/validators.py` (`Symbol`,
   `Timeframe`, `Price`, `Quantity`) and `app/api/params.py`. No bare `str` or
   unbounded `float` for anything a client sends.
10. **Shared loops isolate each item** (savepoint + catch), and anything a user
    can queue into shared state has a per-user cap.
11. **Secrets never reach logs or model output.** Log `type(exc).__name__` for
    failed outbound calls; escape user text at the sink (alerts, exports).
12. **Sessions**: access tokens carry `sid`; ending a session ends its tokens.
    Refresh tokens are consumed atomically. OAuth accounts are bound to
    (provider, subject), not to an email.
13. **Config fails closed.** No published default secret is ever accepted
    without `ALLOW_INSECURE_DEV_DEFAULTS` in development.

When adding a feature, ask who else can reach it, what it shares with other
users, and what happens if the caller sends the worst input. Add an abuse-case
test alongside the happy-path test.

## Agentic layer map (`backend/app/`)
- `agents/tools/` — provider-neutral **tool layer**. Each tool wraps a service
  with a validated Pydantic arg model + uniform `ToolResult`. `ToolRegistry`
  renders specs for OpenAI, Anthropic and MCP. `ToolContext.allow_mutations`
  gates state-changing tools. `build_default_registry()` is the full set.
- `agents/llm/` — **provider-agnostic runtime**. `LLMProvider` with OpenAI and
  Anthropic backends, a `factory` (`auto` prefers Anthropic when a key is set),
  and `AgentRunner`, the bounded observe→call-tools→observe loop.
- `agents/orchestration/` — **LangGraph multi-agent graph**: specialists
  (market, technical, quant, risk) → synthesis → optional paper execution.
- `ml/` — price-direction ML (PyTorch LSTM primary, TensorFlow MLP second
  backend), MLflow tracking, `python -m app.ml.cli`, bash scripts in
  `backend/scripts/`. Pure feature/dataset code is torch-free; runtimes are the
  optional `[ml]` extra.
- `mcp/` — Model Context Protocol server (`python -m app.mcp.server`, `[mcp]`
  extra). Core logic in `handlers.py` is testable without the `mcp` package.

The single-shot advisor (`agents/single_shot.py`, `services/agent_service.py`)
now runs on the same provider runtime as the multi-agent layer, so it works
against any configured backend (Anthropic or OpenAI-compatible), not just OpenAI.

## Running & testing
- Tests run ONLY against the Docker Postgres/Redis stack. Bring it up with
  `docker compose up -d postgres redis redis-broker`, then `./run-tests.sh
  [pytest paths]` from the repo root. There is no local-venv test path (an
  autouse fixture needs Postgres).
- ML tests needing a deep-learning runtime use `pytest.importorskip`; torch is
  NOT in the test image. **On this machine always install the CPU torch wheel**
  (`--index-url https://download.pytorch.org/whl/cpu`) — the default Linux wheel
  is a multi-GB CUDA build that will fill the disk.
- New Celery tasks: follow `workers/runtime.py` and add the module to
  `celery_app.conf.imports` (enforced by `test_celery_registry.py`).

## Conventions
- Services: `__init__(self, session: AsyncSession, client: BinanceClient | None = None)`.
- Routes use the `DBSession` / `CurrentUser` type aliases and `RateLimiter` for
  LLM-cost endpoints.
- Python 3.13, ruff (line length 120), mypy strict. Match surrounding style.

## Commits
This repo uses sequential commits on `main` (`v1..vN`) and feature branches
(the agentic work lives on `agentic-ai`). **Do not put assistant attribution in
commit messages for this repo.**
