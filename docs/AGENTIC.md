# QuantX Agentic AI Layer

QuantX pairs its deterministic trading platform with a **multi-agent AI layer**:
tool-calling LLM agents that reason over the platform's own services, an ML
price-direction model, and a Model Context Protocol server — all behind the same
safety guarantees as the rest of the system.

> **Design principle.** The LLM gets *tools*, never control of money. Every
> agent decision is re-checked by deterministic code, and live trading is never
> reachable from an agent, a graph, or the MCP server.

---

## 1. Tool layer (`app/agents/tools/`)

Each platform capability is wrapped as a **tool**: a name, a description, a
Pydantic argument model, and an `async _run`. A `ToolRegistry` renders the same
tool set into three dialects — OpenAI function calling, Anthropic tool use, and
MCP `inputSchema` — from one definition.

| Group | Tools |
|---|---|
| Market | `get_price`, `get_klines`, `get_indicators` |
| Research/ML | `list_strategies`, `run_backtest`, `predict_direction` |
| Risk | `validate_trade`, `get_risk_state` |
| Execution (paper) | `get_positions`, `submit_paper_order`, `activate_kill_switch` |

Two invariants: **arguments are validated at the edge** (a bad call becomes a
structured error, never an exception), and **mutating tools are refused** unless
`ToolContext.allow_mutations` is set. Live trading is intentionally not a tool.

## 2. Provider-agnostic runtime (`app/agents/llm/`)

A normalized `ChatMessage` / `ToolCall` / `LLMResponse` contract with two
backends — Anthropic (native tool use) and any OpenAI-compatible endpoint
(Ollama, Groq, Gemini, OpenAI). `build_provider()` resolves the configured
choice (`auto` prefers Anthropic when a key is present). `AgentRunner` runs the
bounded **observe → call tools → observe** loop with a hard iteration ceiling
and a full tool-invocation trace.

## 3. Multi-agent orchestration (`app/agents/orchestration/`)

A LangGraph `StateGraph`:

```
START → init → market → technical → quant → risk → synthesis → [execute?] → END
```

- **init** captures a numeric reference price.
- **market / technical / quant** specialists each run the tool-calling loop with
  only their role's tools (the quant agent may call the ML `predict_direction`
  and `run_backtest`).
- **risk** reads persisted risk state and sets a hard `halted` flag.
- **synthesis** emits one decision, re-validated by `AIDecisionValidator`; a
  halt, missing price, or failed check → `WAIT`.
- **execution** places a *paper* order only when mutations are enabled, the
  decision is actionable, and trading is not halted.

Exposed over HTTP: `POST /api/v1/agent/orchestrate?symbol=BTCUSDT[&execute=true]`.

## 4. ML models + MLOps (`app/ml/`)

Next-bar-direction classification:

- **Features** (pure pandas/numpy): multi-horizon returns, realized volatility,
  high-low range, volume z-score, SMA ratio, RSI(14); next-bar label. No
  look-ahead.
- **Models**: PyTorch LSTM (primary) and a TensorFlow Keras MLP (second backend)
  behind one training/inference contract.
- **Training** writes weights + a metadata sidecar (feature list, sequence
  length, scaler stats, metrics, provenance) and logs an MLflow run.
- **Inference** loads the latest artifact and scores the current window; the
  metadata guarantees inference input matches training.

Operate it:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU wheel
pip install -e '.[ml]'
docker compose exec backend scripts/train_model.sh BTCUSDT 1h torch 20
docker compose exec backend scripts/eval_model.sh  BTCUSDT 1h torch
# or: python -m app.ml.cli train|evaluate|predict --symbol BTCUSDT --timeframe 1h
```

The deep-learning runtimes live in the optional `[ml]` extra, kept out of the
core/test image (plain-PyPI torch on Linux is a multi-GB CUDA build).

## 5. MCP server (`app/mcp/`)

Serves the tool registry over the Model Context Protocol so Claude Code and
other MCP clients can drive QuantX.

```bash
pip install -e '.[mcp]'
python -m app.mcp.server
```

Identity and the mutation permission are bound from the environment at start-up
(`QUANTX_MCP_USER_ID`, `QUANTX_MCP_ALLOW_MUTATIONS`), never from the client — so
a remote client cannot escalate. The protocol-free core (`handlers.py`) is
unit-tested without the `mcp` package.

## 6. Agent Skills (`.claude/skills/`)

Repeatable Claude Code workflows: `quantx-analyze`, `quantx-train-model`,
`quantx-mcp-serve`.

---

## Safety recap

1. Mainnet interlock: real orders need BOTH `BINANCE_TESTNET=false` AND
   `ALLOW_MAINNET_TRADING=true`.
2. No agent/graph/MCP path can place a live order — paper only, gated on
   `allow_mutations`.
3. `AIDecisionValidator` and `RiskManager` are deterministic and
   non-overridable. The model proposes; math and explicit flags decide.

## Tech

Multi-agent systems · agent orchestration (LangGraph) · tool calling · Model
Context Protocol · Agent Skills / Claude Code · TensorFlow · PyTorch · MLOps
(MLflow) · FastAPI · PostgreSQL/SQL · Celery · Redis · Docker/Linux · Bash · Git.
