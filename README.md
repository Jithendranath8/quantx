# QuantX — AI Quantitative Trading Research & Execution Platform

A FastAPI + React platform for quantitative trading research: market data
ingestion, technical analysis, strategy backtesting, paper trading, an AI
analyst with deterministic validation, and Binance SPOT execution behind a
persisted risk engine.

> **Trading safety.** Placing real orders requires **both**
> `BINANCE_TESTNET=false` **and** `ALLOW_MAINNET_TRADING=true`. Either flag
> alone keeps the platform on testnet. This interlock exists so a single
> misconfigured environment variable cannot move real money.

**Read [`project_state.md`](project_state.md) before building on this.** It
lists precisely what is implemented and what is not.

---

## Architecture

```
                    ┌──────────────┐
                    │   Frontend   │  React 18 + Vite + Tailwind
                    │  (nginx :80) │  18 pages, all API-driven
                    └──────┬───────┘
                           │ /api  /ws   (nginx proxy)
                    ┌──────▼───────┐
                    │   Backend    │  FastAPI + SQLAlchemy 2 (async)
                    │   (:8000)    │  JWT auth, per-user isolation
                    └──┬────┬───┬──┘
          ┌────────────┘    │   └────────────┐
   ┌──────▼──────┐  ┌───────▼──────┐  ┌──────▼───────┐
   │ PostgreSQL  │  │ Redis cache  │  │ Redis broker │
   │  (schema,   │  │ (rate limit, │  │ (Celery,     │
   │   history)  │  │  pub/sub)    │  │  noeviction) │
   └─────────────┘  └──────────────┘  └──────┬───────┘
                                             │
                              ┌──────────────▼─────────────┐
                              │ Celery worker + beat       │
                              │ downloads, retention,      │
                              │ reconciliation, health     │
                              └────────────────────────────┘
```

Two Redis instances is deliberate: the cache evicts under pressure (`allkeys-lru`),
the broker must not (`noeviction`), because an evicted message is a background
job that disappears without an error.

---

## Subsystems

| Subsystem | What it does |
|---|---|
| **Auth** | JWT access tokens, rotating refresh tokens with reuse detection, bcrypt password hashing |
| **Market data** | Binance SPOT REST, historical OHLCV backfill, optional WebSocket ingestion to Redis pub/sub, scheduled funding-rate and open-interest ingestion |
| **Indicators** | SMA, EMA, RSI, MACD, Bollinger, ATR, ADX, VWAP, Stochastic, OBV, Ichimoku — Wilder smoothing where the standard requires it |
| **Strategies** | EMA crossover, RSI mean reversion, MACD momentum, Bollinger breakout, MTF trend; parameterizable for search |
| **Risk engine** | Per-trade risk, daily loss, leverage, exposure, concurrency; circuit breaker persisted per user in PostgreSQL |
| **Paper trading** | Live prices, slippage, fees, BUY/SELL, MARKET plus resting LIMIT/STOP_LOSS/TAKE_PROFIT orders, position averaging, realized PnL |
| **Live trading** | HMAC-signed Binance SPOT orders, local pre-flight against symbol filters, durable order records |
| **Kill switch** | Halts first, cancels open orders, verifies each cancellation, reports failures explicitly |
| **Backtesting** | Event-driven, long/short, intrabar SL/TP, fees, slippage, timeframe-aware Sharpe |
| **Research** | Walk-forward, grid/random/TPE parameter search, Monte Carlo, look-ahead bias audit — all over real backtests, auto-registered against a content hash of the data |
| **AI agent** | Structured market context → decision, re-validated against backend arithmetic; failed validation becomes WAIT. Runs against OpenAI, a local Ollama model, Gemini, Groq or any OpenAI-compatible endpoint. Decisions are settled by forward test, so win rate is measured rather than assumed |
| **Observability** | Event ledger, Prometheus metrics (authenticated), live health probes |

---

## Getting started

### AI provider — no paid account required

The agent speaks the OpenAI chat-completions API, so any compatible endpoint
works. The cheapest option is a model on your own machine:

```bash
brew install ollama && ollama serve &
ollama pull qwen2.5:3b
```

Then in `.env`:

```
OPENAI_BASE_URL=http://host.docker.internal:11434/v1
OPENAI_MODEL=qwen2.5:3b
OPENAI_API_KEY=
```

No key, no account, no per-token cost. Google Gemini and Groq both have free
tiers and work the same way — see `.env.example` for their base URLs.

`qwen2.5:3b` (1.9 GB) is the smallest model verified to produce coherent,
validator-passing decisions here. A 1B model also runs, but gets its own
risk:reward arithmetic wrong often enough that most decisions are rejected.

That rejection is the system working, not failing: the deterministic validator
recomputes each risk:reward from the model's own prices and downgrades a
mismatched decision to WAIT, so a weak model fails safely instead of emitting a
confidently wrong trade. Expect roughly 15s per decision on a laptop.

### Prerequisites

- Docker and Docker Compose
- For local development: Python 3.12+ and Node 20+

### Run the stack

```bash
git clone <repository-url> && cd AI-Trading-Research-Platform
```

Create your environment file. `POSTGRES_PASSWORD`, `REDIS_PASSWORD`,
`SECRET_KEY`, `JWT_SECRET_KEY` and `GRAFANA_ADMIN_PASSWORD` are required —
compose refuses to start without them.

```bash
cp .env.example .env
```

Generate secrets:

```bash
python3 -c "import secrets; [print(f'{k}={secrets.token_urlsafe(48)}') for k in ('SECRET_KEY','JWT_SECRET_KEY','POSTGRES_PASSWORD','REDIS_PASSWORD','GRAFANA_ADMIN_PASSWORD')]"
```

Prometheus authenticates to `/metrics` using `SECRET_KEY`, read from a file:

```bash
grep '^SECRET_KEY=' .env | cut -d= -f2- | tr -d '\n' > monitoring/prometheus/metrics_password
```

Start everything. Migrations run automatically before the API starts:

```bash
docker compose up -d --build
```

Then open:

- Frontend — http://localhost:5173
- API docs — http://localhost:8000/docs (development only)
- Prometheus — http://localhost:9090
- Grafana — http://localhost:3000

PostgreSQL and Redis are intentionally **not** published to the host. Use
`docker compose exec postgres psql -U quantx` for administrative access.

### Local development

Datastores in Docker, application on the host with hot reload:

```bash
docker compose -f docker-compose.dev.yml up -d
```

```bash
cd backend && pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

```bash
cd frontend && npm ci && npm run dev
```

---

## Tests

```bash
cd backend
ruff check .
alembic upgrade head && alembic downgrade base && alembic upgrade head
pytest tests/ -v --cov=app
```

```bash
cd frontend
npm run typecheck && npm run lint && npm run build
```

The backend suite needs PostgreSQL and Redis running, and creates a
`quantx_test` database.

---

## Production checklist

- [ ] `APP_ENV=production` and `DEBUG=false`. The app refuses to start in
      production with debug on, default secrets, or an empty `REDIS_PASSWORD`.
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
