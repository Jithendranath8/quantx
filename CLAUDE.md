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

The single-shot advisor (`agents/trading_agent.py`, `services/agent_service.py`)
still exists; the agentic layer is additive.

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
