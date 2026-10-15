---
name: quantx-mcp-serve
description: Run or register the QuantX MCP server so Claude Code (or any MCP client) can call the platform's tools — prices, indicators, backtests, risk checks, ML predictions, paper orders. Use when asked to expose QuantX over MCP, connect it to Claude Code, or debug the MCP server.
---

# QuantX MCP server

Serve the QuantX tool registry over the Model Context Protocol (stdio).

## Install & run
```bash
pip install -e '.[mcp]'
python -m app.mcp.server
```

## Register in an MCP client
Command `python`, args `["-m", "app.mcp.server"]`, with environment:

| Env var | Meaning | Default |
|---|---|---|
| `QUANTX_MCP_USER_ID` | bind calls to this user UUID (needed for user-scoped tools) | unset |
| `QUANTX_MCP_ALLOW_MUTATIONS` | `true` to permit paper-order / kill-switch tools | false |
| `QUANTX_MCP_ACCOUNT_BALANCE` | balance assumed for risk sizing | 100000 |

Plus the usual DB/Redis/Binance env the backend needs.

## Safety model (do not weaken)
- Identity and the mutation permission are bound from the environment at
  start-up, never from the client — an MCP client cannot escalate.
- Live trading is NOT exposed. Only paper trading and the kill switch are
  mutating, and both require `QUANTX_MCP_ALLOW_MUTATIONS=true`.
- Every tool still passes argument validation and the deterministic risk
  engine. The LLM/client gets tools, never direct control of real money.

## Debugging
The protocol-free core is `app/mcp/handlers.py` (unit-tested without the `mcp`
package). If a tool misbehaves over MCP, reproduce it against `handle_call`
first to isolate transport issues from tool logic.
