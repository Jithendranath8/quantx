# QuantX — Agentic AI Quantitative Trading Platform

QuantX is a production-style quantitative trading platform with a **multi-agent
AI layer**. It combines market-data ingestion, technical analysis, strategy
backtesting, a research suite, paper and live Binance SPOT execution behind a
persisted risk engine — and a system of tool-calling LLM agents, an ML
price-direction model, and a Model Context Protocol server on top.

**Stack:** FastAPI · SQLAlchemy 2 (async) · PostgreSQL · Redis · Celery · React
18 · LangGraph · PyTorch / TensorFlow · MLflow · Model Context Protocol · Docker.

---

## Safety model

QuantX treats the LLM as an advisor, never as an authority over money. Two
guarantees are load-bearing and enforced in code:

- **Mainnet interlock.** Placing real orders requires **both**
  `BINANCE_TESTNET=false` **and** `ALLOW_MAINNET_TRADING=true`. Either flag alone
  keeps the platform on testnet, so a single misconfigured variable cannot move
  real funds.
- **Agents get tools, not control.** Every agent decision is re-checked by a
  deterministic validator and the risk engine before it can act, and live
  trading is never reachable from an agent, the orchestration graph, or the MCP
  server. Agents can place **paper** orders only, and only when explicitly
  permitted.

> See [`project_state.md`](project_state.md) for an honest, verified account of
> what is and isn't implemented, and [`docs/AGENTIC.md`](docs/AGENTIC.md) for the
> full agentic-layer design.

---

## Architecture

```
            React 18 + Vite + Tailwind (nginx :80) ── 18 API-driven pages
                               │ /api  /ws
                    ┌──────────▼───────────┐
                    │   FastAPI backend    │  async SQLAlchemy 2, JWT auth,
                    │       (:8000)        │  per-user isolation
                    └──┬───────┬────────┬──┘
             ┌─────────┘       │        └──────────┐
      ┌──────▼─────┐   ┌───────▼──────┐    ┌────────▼───────┐
      │ PostgreSQL │   │ Redis cache  │    │  Redis broker  │
      │  (history) │   │ (lru, pubsub)│    │  (noeviction)  │
      └────────────┘   └──────────────┘    └───────┬────────┘
                                                   │
                                        ┌──────────▼──────────┐
                                        │ Celery worker + beat│
                                        └─────────────────────┘

   Agentic layer (on top of the backend services)
   ┌─────────────────────────────────────────────────────────────────┐
   │  Tool registry → provider-agnostic runtime (Claude / OpenAI-compat)│
   │  → LangGraph graph: market · technical · quant · risk → synthesis │
   │  ML model (PyTorch/TensorFlow + MLflow)   MCP server (Claude Code) │
   └─────────────────────────────────────────────────────────────────┘
```

Running two Redis instances is deliberate: the cache evicts under pressure
(`allkeys-lru`) while the broker must not (`noeviction`), because an evicted
message is a background job that silently disappears.

---

## Capabilities

| Subsystem | Summary |
|---|---|
| **Auth** | JWT access tokens, rotating refresh tokens with reuse detection, bcrypt hashing |
| **Market data** | Binance SPOT REST, historical OHLCV backfill, optional WebSocket ingestion, scheduled funding-rate and open-interest capture |
| **Indicators** | SMA, EMA, RSI, MACD, Bollinger, ATR, ADX, VWAP, Stochastic, OBV, Ichimoku (Wilder smoothing where required) |
| **Strategies** | EMA crossover, RSI mean reversion, MACD momentum, Bollinger breakout, multi-timeframe trend — parameterizable for search |
| **Risk engine** | Per-trade risk, daily loss, leverage, exposure, concurrency; circuit breaker persisted per user |
| **Paper trading** | Live prices, slippage, fees, MARKET + resting LIMIT/STOP_LOSS/TAKE_PROFIT, position averaging, realized PnL |
| **Live trading** | HMAC-signed Binance SPOT orders, symbol-filter pre-flight, durable order records (testnet by default) |
| **Kill switch** | Halts first, cancels open orders, verifies each cancellation, reports failures explicitly |
| **Backtesting** | Event-driven, long/short, intrabar SL/TP, fees, slippage, timeframe-aware Sharpe |
| **Market making** | Avellaneda–Stoikov inventory-aware quoting simulated over candles — reservation-price skew, hard inventory cap, no look-ahead, spread-capture vs inventory P&L decomposition |
| **Research** | Walk-forward, grid/random/TPE search, Monte Carlo, look-ahead bias audit, auto-registered against a content hash of the data |
| **Agentic AI** | Multi-agent LangGraph orchestration over a tool-calling runtime (Claude or any OpenAI-compatible model); deterministic validation on every decision |
| **ML / MLOps** | PyTorch LSTM + TensorFlow MLP price-direction model, MLflow tracking, exposed to the agents as a prediction tool |
| **MCP server** | Exposes the platform's tools over the Model Context Protocol for Claude Code and other clients |
| **Observability** | Event ledger, authenticated Prometheus metrics, live health probes |

---

## Agentic AI layer

A system of specialist agents reasons over the platform's own services. The LLM
is given **tools** — typed, validated wrappers around real capabilities (prices,
indicators, backtests, risk checks, ML predictions, paper execution) — and runs a
bounded reasoning loop under a LangGraph supervisor:

```
init → market → technical → quant → risk → synthesis → [paper execution]
```

- **Provider-agnostic.** Runs against Anthropic Claude or any OpenAI-compatible
  endpoint (OpenAI, local Ollama, Groq, Gemini), switchable by configuration.
- **Specialist roles.** Each agent is given only the tools its role needs; the
  quant agent may call the ML model and backtester.
- **Deterministic gate.** The synthesis step's decision is re-validated against
  backend arithmetic; a halt, missing price, or failed check becomes `WAIT`.

Run it over HTTP once a provider is configured:

```bash
POST /api/v1/agent/orchestrate?symbol=BTCUSDT
```

Full design and component map: [`docs/AGENTIC.md`](docs/AGENTIC.md).

---

## Quick start

### Prerequisites

- Docker and Docker Compose
- For local development: Python 3.13 and Node 20+

### 1. Configure

```bash
git clone <repository-url> && cd AI-Trading-Research-Platform
cp .env.example .env
```

`POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `SECRET_KEY`, `JWT_SECRET_KEY` and
`GRAFANA_ADMIN_PASSWORD` are required — Compose refuses to start without them.
Generate them:

```bash
python3 -c "import secrets; [print(f'{k}={secrets.token_urlsafe(48)}') for k in ('SECRET_KEY','JWT_SECRET_KEY','POSTGRES_PASSWORD','REDIS_PASSWORD','GRAFANA_ADMIN_PASSWORD')]"
```

Prometheus authenticates to `/metrics` with `SECRET_KEY`, read from a file:

```bash
grep '^SECRET_KEY=' .env | cut -d= -f2- | tr -d '\n' > monitoring/prometheus/metrics_password
```

### 2. Run

Migrations run automatically before the API starts:

```bash
docker compose up -d --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API docs | http://localhost:8000/docs (development only) |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |

PostgreSQL and Redis are intentionally **not** published to the host; use
`docker compose exec postgres psql -U quantx` for administrative access.

---

## Configuring the AI provider

The agents need an LLM. Any of these works; none requires a paid account.

**Local model (no key, no cost)** — the cheapest option:

```bash
brew install ollama && ollama serve &
ollama pull qwen2.5:3b
```

```ini
OPENAI_BASE_URL=http://host.docker.internal:11434/v1
OPENAI_MODEL=qwen2.5:3b
OPENAI_API_KEY=
```

**Anthropic Claude** (strongest reasoning):

```ini
LLM_PROVIDER=auto
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-5-5
```

Gemini and Groq have free tiers and work the same way — see `.env.example` for
their base URLs. Small local models are weak at arithmetic, which is by design
safe here: the deterministic validator recomputes each risk:reward from the
model's own prices and downgrades a mismatched decision to `WAIT`, so a weak
model fails safely rather than emitting a confidently wrong trade.

---

## Optional components

### Machine learning (PyTorch / TensorFlow + MLflow)

The deep-learning runtimes live in an optional extra to keep the core images
lean. On CPU/Mac, install the CPU-only torch wheel to avoid the multi-gigabyte
CUDA build:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e '.[ml]'

# train / evaluate on stored candles
docker compose exec backend scripts/train_model.sh BTCUSDT 1h torch 20
docker compose exec backend scripts/eval_model.sh  BTCUSDT 1h torch
```

### MCP server (Claude Code)

```bash
pip install -e '.[mcp]'
python -m app.mcp.server
```

Identity and permissions are bound from the environment at start-up, never from
the client. See the `quantx-mcp-serve` skill and [`docs/AGENTIC.md`](docs/AGENTIC.md).

---

## Development

Datastores in Docker, application on the host with hot reload:

```bash
docker compose -f docker-compose.dev.yml up -d

cd backend && pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload

cd frontend && npm ci && npm run dev
```

## Testing

The backend suite runs against PostgreSQL and Redis in Docker and creates a
`quantx_test` database. The helper script builds the image and wires everything
up:

```bash
./run-tests.sh                        # full backend suite
./run-tests.sh tests/unit/test_risk.py   # a subset

cd frontend && npm run typecheck && npm run lint && npm run build
```

ML tests that require a deep-learning runtime are skipped automatically when it
is not installed, so the core suite stays fast and lean.

---

## Production checklist

- [ ] `APP_ENV=production` and `DEBUG=false` (the app refuses to start in
      production with debug on, default secrets, or an empty `REDIS_PASSWORD`).
- [ ] Unique, randomly generated `SECRET_KEY` and `JWT_SECRET_KEY`.
- [ ] `ALLOW_MAINNET_TRADING=false` unless you intend to trade real funds.
- [ ] `ALLOWED_ORIGINS` set to your actual frontend origin, not localhost.
- [ ] TLS terminated in front of nginx; run uvicorn with `--proxy-headers`.
- [ ] Connection budget checked: `(DB_POOL_SIZE + DB_MAX_OVERFLOW) ×
      (API workers + Celery workers)` below PostgreSQL `max_connections`.
- [ ] `RETENTION_*_DAYS` reviewed; the nightly prune keeps tables bounded.
- [ ] Celery beat running, so retention, reconciliation, derivatives ingestion,
      AI settlement and resting paper-order fills all fire.
- [ ] Backups configured for the `postgres_data` volume.
- [ ] Alerting configured (`ALERT_WEBHOOK_URL` or Telegram) so kill-switch and
      health-check failures reach a human.
