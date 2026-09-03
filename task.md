# QuantX — Task List

Checked items are verified by a passing test or an executed command, not by
having been written. See `project_state.md` for what is and is not implemented.

## Foundations

- [x] Project setup, configuration, structured logging
- [x] Database schema and migrations (001–005, upgrade and downgrade verified)
- [x] Authentication: JWT, rotating refresh tokens, reuse detection
- [x] Authorization: per-user ownership on every resource
- [x] Rate limiting on authentication and expensive endpoints

## Market data

- [x] Binance SPOT REST connector with HMAC-SHA256 signing
- [x] Historical OHLCV download with batch commits and request pacing
- [x] Multi-timeframe indicator engine (validated and capped)
- [x] WebSocket ingestion + Redis pub/sub fan-out (off by default)
- [x] Funding rate / open interest ingestion (scheduled snapshot + backfill)
- [ ] Order-flow and liquidation ingestion
- [ ] News and macro sentiment pipeline

## Analysis

- [x] 14 technical indicators; Wilder smoothing for RSI, ATR, ADX
- [x] Strategy registry with parameterized construction
- [x] AI agent with structured context, real token/latency/cost accounting
- [x] Deterministic AI decision validator
- [x] AI decision settlement by forward test (real win rate and expectancy)
- [ ] Market regime classification
- [ ] Portfolio correlation and cluster exposure

## Execution

- [x] Risk engine with persisted per-user circuit breaker
- [x] Paper trading: BUY and SELL, fees, slippage, position averaging
- [x] Live trading: signed Binance SPOT orders, testnet-locked by default
- [x] Kill switch: cancels, verifies, and reports failures honestly
- [x] Order reconciliation against exchange state
- [ ] Futures trading (public funding/OI reads only; no futures execution)
- [x] LIMIT / STOP_LOSS / TAKE_PROFIT resting orders with a fill engine
- [ ] OCO orders and partial fills

## Research

- [x] Event-driven backtester: long/short, SL/TP, fees, slippage
- [x] Timeframe-aware Sharpe and Sortino annualization
- [x] Walk-forward testing over real backtests
- [x] Grid and random parameter search over real backtests
- [x] Monte Carlo bootstrap resampling (seeded, reproducible)
- [x] Look-ahead bias detection by differential execution
- [x] TPE sequential model-based optimization (discrete grids)
- [x] Dataset fingerprinting over actual candle values, wired into research runs
- [x] Automatic experiment registration with git commit and row count

## Platform

- [x] Frontend: all 18 pages calling the API, no mock data
- [x] Refresh-token rotation in the browser client
- [x] Event ledger with a read API and UI
- [x] Health center probing every subsystem for real
- [x] Prometheus metrics behind authentication
- [x] Retention pruning and token cleanup workers
- [x] Docker compose with migrations, split Redis, no exposed datastores
- [x] CI that fails on lint, typecheck, test, migration, or build errors
- [x] WebSocket-driven live prices on Market Data
- [ ] WebSocket updates for positions, orders and PnL screens
- [ ] Grafana dashboards beyond the datasource provisioning
