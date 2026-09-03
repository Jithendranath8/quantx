# QuantX — Project State

**Last verified: 2026-09-02** by running the test suite, the migrations, and the
application against PostgreSQL 16 and Redis 7.

This file describes what the code actually does. A previous version claimed
"Overall Completion: 100%" across 40 phases while the application could not
start, every insert against PostgreSQL failed, and the entire frontend was
hardcoded. Please keep this document honest: an inaccurate state file is worse
than no state file, because it causes people to build on things that do not work.

---

## Status summary

| Area | State |
|---|---|
| Backend API | Working. 60 operations, 332 tests passing, 81% coverage. |
| Database | Working. Migrations 001–007 apply and reverse cleanly. |
| Authentication | Working. JWT with rotating refresh tokens and reuse detection. |
| Paper trading | Working. MARKET, LIMIT, STOP_LOSS, TAKE_PROFIT; fees, slippage, per-user isolation. |
| Live trading | Implemented against Binance SPOT, **testnet only by default**. |
| Risk engine | Working. Limits enforced; circuit breaker persisted per user. |
| Backtesting | Working. Event-driven, long/short, SL/TP, fees, slippage. |
| Research suite | Working. Walk-forward, grid/random/TPE search, Monte Carlo, bias audit, auto-registered with dataset fingerprints. |
| Indicators | Working. 14 indicators, Wilder smoothing for RSI/ATR/ADX. |
| AI agent | Implemented against any OpenAI-compatible endpoint (OpenAI, local Ollama, Gemini, Groq). Degrades to WAIT when unconfigured or when the provider fails. Decisions are settled by forward test, so win rate is measured. |
| Frontend | Working. All 18 pages call the API; Market Data streams over WebSocket. Builds, typechecks, lints clean. |
| Market data ingestion | Working. Closed bars are written to the database straight from the live stream, so stored history trails real time by one bar. The 10-minute REST sync remains as backfill and gap repair; funding rate and open interest on their own schedule. Live WebSocket stream is off by default (`MARKET_STREAM_ENABLED`). |
| Monitoring | Prometheus metrics (authenticated) + Grafana provisioning. |
| Deployment | `docker compose up` builds and runs end to end, verified. Migrations run automatically before the API starts. |

---

## What is real

**Authentication and access control.** Registration, login, JWT access tokens,
rotating refresh tokens with reuse detection, and per-user ownership checks on
every resource. All 46 protected API operations reject anonymous and forged
tokens; this is covered by a parametrised test so it cannot regress quietly.

**Risk engine.** Max risk per trade, max daily loss, max leverage, portfolio
exposure, and concurrent-trade limits. `RiskManager.validate_trade` is pure; the
circuit breaker lives in the `risk_state` table, so a halt applies across every
worker process and survives a restart. It is checked before any exchange call.

**Paper trading.** Real market prices from Binance, 0.05% slippage against the
taker, 0.075% fees, BUY and SELL, position averaging, partial closes, realized
PnL. Every account operation verifies ownership.

**Live trading.** HMAC-SHA256 signed Binance SPOT requests: `place_order`,
`cancel_order`, `get_open_orders`, `get_order`, `get_account`. Orders are
written to `live_orders` with a locally generated `client_order_id` *before*
submission, so an indeterminate result is recoverable. Pre-flight checks snap
quantity and price to the symbol's filters and validate min-notional locally.

**Kill switch.** Persists the halt first, then cancels the user's open exchange
orders, then re-reads each one to confirm it reached a terminal state. Reports
`fully_successful: false` and lists the errors when any cancellation cannot be
confirmed.

**Backtesting.** Event-driven, long and short, intrabar stop-loss and
take-profit (stop assumed first when both fall in one bar), entry and exit fees,
slippage, and end-of-data position closing. The strategy receives only its
declared `lookback` rows per bar. Sharpe and Sortino are annualized from the
actual timeframe.

**Research suite.** Walk-forward runs a real backtest on each train and test
window. Optimization expands the parameter grid and backtests every candidate.
Monte Carlo bootstrap-resamples the strategy's own realized trade PnLs with a
fixed seed. The bias detector executes the strategy twice per sampled bar — once
on truncated history, once with the full series — and reports any disagreement.

**Derivatives ingestion.** Funding rates and open interest are fetched from
Binance and stored, so the AI agent receives real values instead of nulls. A
half-hourly snapshot keeps them fresh and a nightly backfill closes gaps.
Binance only retains about 30 days of open-interest history, so a backfill
cannot reach further back than that.

**AI outcome settlement.** Every decision is settled by forward-testing it
against subsequent stored candles: whichever of stop or target the market
reached first, with the stop assumed on a tie. Results carry
``outcome_source='SIGNAL_FORWARD_TEST'`` and are expressed per $1,000 of
notional, so a hypothetical signal result can never be mistaken for money made.
WAIT decisions settle at exactly zero and are excluded from win rate.

**Reproducible research.** Walk-forward and optimization runs register
themselves in the experiment registry with a SHA-256 fingerprint of the actual
candle values, the row count, and the git commit. Two runs over the same data
share a dataset_version, which is what makes a past result checkable.

**Resting paper orders.** LIMIT, STOP_LOSS and TAKE_PROFIT orders rest as
PENDING until the market reaches their level. A limit fills at its resting
price; a stop fills at the market it triggered into, because filling at the
trigger would model a guarantee the exchange does not give. Balance is
re-checked at trigger time, since nothing is reserved at placement.

**Live UI streaming.** The Market Data page subscribes to the WebSocket gateway
and falls back to REST polling when ingestion is disabled. Verified end to end:
Binance -> normalizer -> Redis pub/sub -> authenticated gateway -> browser.

**Stored candles come off the stream.** The same normalized messages that feed
the ticker are buffered and upserted as soon as a bar closes. Previously the
stream only published to Redis, so the price display was live while stored
history advanced only on the 10-minute REST sync -- charts sat up to ten
minutes behind the quoted price. Measured after the change, every timeframe
trails real time by exactly one bar, which is the floor for closed candles.

**One worker owns ingestion.** FastAPI's lifespan runs in all
`BACKEND_WORKERS` processes, so the stream previously opened one Binance socket
per worker and wrote every candle four times over. Ownership is now a Redis key
under a TTL that the owner renews; if it dies, a follower claims it within
`LOCK_TTL_SECONDS`. Renewal and release are compare-and-swap against the owner
token, so a worker stalled past its TTL cannot clobber a successor's lock. The
owner publishes stream metrics to Redis because health requests land on an
arbitrary worker and in-process counters read zero in the other three.

**Provider-agnostic AI.** `OPENAI_BASE_URL` points the agent at any endpoint
speaking the OpenAI chat-completions API, so the feature does not depend on
OpenAI billing. A base_url alone is sufficient; a self-hosted model needs no
credential. Cost reporting returns 0.0 for local endpoints and for models whose
price is unknown, rather than inferring a figure at the gpt-4o rate.

**Compact prompts.** The context sent to the model is trimmed to 20 candles and
a fixed indicator set, with floats rounded: ~3,100 characters against ~13,000
before. The original overflowed a small model's context window outright, and on
a paid provider it billed sixteen digits of precision on every call.

**Health reporting.** Every subsystem is probed live: a SQL round trip, a Redis
PING, a Celery broker ping, a Binance ping, market-data freshness, gateway
connection count, and the persisted risk state. Each carries a boolean verdict
that can be false.

---

## What is NOT implemented

Be explicit about these rather than discovering them later.

- **Mainnet trading is blocked by default.** Placing real orders requires BOTH
  `BINANCE_TESTNET=false` AND `ALLOW_MAINNET_TRADING=true`. One flag alone is
  not enough, by design.
- **Futures trading.** Only Binance SPOT execution is implemented. The futures
  host is used for *public* funding-rate and open-interest reads only; no
  futures order, position, margin or leverage endpoint is wired.
- **Order-flow, liquidation, news, and market-regime engines.** These modules
  were deleted. They had no call sites and returned fabricated values. Their
  tables (`order_flow_snapshots`, `liquidation_events`, `news_articles`,
  `funding_oi_records`) still exist but **nothing writes to them**.
- **News sentiment.** No pipeline. The agent's `news_summary` is an empty list.
- **AI settlement is a forward test, not trading performance.** Win rate and
  expectancy measure whether a signal's own stop or target was reached first on
  stored 1h candles. They do not mean the platform made or lost that money, and
  they assume a fill at exactly the stated level. Read `outcome_source` before
  quoting the number.
- **AI settlement needs 1h candles for the symbol.** Decisions on a symbol with
  no stored history stay unsettled rather than being resolved by guesswork.
- **Gaussian-process optimization.** TPE (sequential model-based) is
  implemented over discrete grids. There is no continuous-space GP optimizer.
- **Paper trading is long-only.** Shorting is supported in the *backtester* but
  not in paper trading, which has no margin ledger. OCO orders and partial
  fills are also not implemented, and resting orders are evaluated against the
  last trade price, not the order book.
- **Live-order stop-loss and take-profit are not auto-managed.** The fields are
  accepted and stored, but nothing places or monitors protective orders on the
  exchange.
- **WebSocket streaming covers Market Data only.** Positions, orders and PnL
  screens poll REST. Ingestion is off unless `MARKET_STREAM_ENABLED=true`.
- **Grafana dashboards.** Only the Prometheus datasource is provisioned; no
  dashboards ship with the repo.

## Known operational constraints

- **Connection budget.** Pool sizing is per process. Total PostgreSQL
  connections are `(DB_POOL_SIZE + DB_MAX_OVERFLOW) × (API workers + Celery
  workers)`. Defaults are 5+5 per process; compose raises `max_connections` to
  200. Recalculate before scaling workers.
- **Redis split.** The cache instance uses `allkeys-lru`; the Celery broker uses
  `noeviction`. Do not merge them — an evicting broker silently drops jobs.
- **Retention.** `candles`, `event_ledger`, `audit_logs`, and `ai_decision_logs`
  are pruned nightly by `app.workers.maintenance.prune_expired_data` using the
  `RETENTION_*_DAYS` settings. Setting one to 0 disables pruning for that table.
- **Rate limits.** Fixed-window per client IP, backed by Redis, failing open if
  Redis is unavailable. `X-Forwarded-For` is not trusted; run behind a proxy
  with `--proxy-headers` for accurate client IPs.
- **Python version.** Docker images use 3.13; the code requires 3.12+ for PEP
  695 generics in `app/workers/runtime.py`.
- **Celery task registry is an explicit list.** `app/core/celery_app.py` names
  each worker module in `conf.imports`. Autodiscovery does not work here: it
  looks for a `tasks` submodule per package, so the worker would start with an
  empty registry and reject every scheduled job. Add new worker modules to that
  list; `test_celery_registry.py` fails if a scheduled task is unregistered.
- **All backend services share one image** (`quantx-backend:local`). Without an
  explicit `image:` name, Compose builds a separate image per service and
  `docker compose build backend` silently leaves the Celery workers on stale
  code.
- **nginx re-resolves the backend per request.** An `upstream` block caches the
  container IP at startup, so any backend restart would 502 the whole frontend
  until nginx itself restarted.
- **Testnet WebSockets live on `stream.testnet.binance.vision`**, not on
  `testnet.binance.vision` (which serves REST and answers 404 to an upgrade).
- **Public market data always reads mainnet**, regardless of `BINANCE_TESTNET`.
  Testnet retains roughly 28 days of kline history against mainnet's 400+,
  which silently capped every backtest and research run to under a month.
  Klines, ticker and order book read mainnet; `get_price`, `exchangeInfo` and
  all order flow stay on the trading venue so pre-flight checks match where the
  order actually lands.
- **Blank is not unset for the OpenAI SDK.** `.env.example` ships
  `OPENAI_BASE_URL=` empty, and the SDK reads that variable itself, so passing
  `None` does not restore the default -- the client ends up addressing no host.
  The agent passes `api.openai.com` explicitly, and blank `OPENAI_BASE_URL` /
  `OPENAI_MODEL` values are coerced back to their defaults in config.
- **`MARKET_SYMBOLS` / `MARKET_TIMEFRAMES` are the single source of truth** for
  the API's symbol list, the WebSocket stream, and the scheduled backfill. The
  UI cannot offer a pair that nothing ingests. `sync_market_data` tops up every
  pair every 10 minutes.
- **AI health is judged from recent decisions, not key presence.** A key can be
  valid but out of credit; the agent degrades to WAIT on any provider error, so
  an all-WAIT window is reported as DEGRADED.

---

## Verification

```bash
./run-tests.sh                    # 411 passed
./run-tests.sh tests/unit -k leader
```

`run-tests.sh` runs the suite in the dev image against the Compose network. It
deliberately overrides the live settings the tests assert about -- rate
limiting, `MARKET_STREAM_ENABLED`, and the AI provider -- and points Redis at
db 9. Running pytest against the live environment instead produces failures
that have nothing to do with the code: 429s from the running app's rate-limit
counters, and "not configured" assertions failing because a provider is in
fact configured.

Only one pytest session at a time per test database: the schema fixture is
session-scoped and destructive. Use TEST_DATABASE_URL for a parallel run.

```bash
cd backend
ruff check .                      # clean
alembic upgrade head              # 001 → 007
```

```bash
cd frontend
npm ci && npm run typecheck && npm run lint && npm run build   # all clean
```
