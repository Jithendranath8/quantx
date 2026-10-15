---
name: quantx-analyze
description: Run QuantX's multi-agent analysis for a trading symbol — market, technical, quant and risk specialists under a LangGraph supervisor, producing one deterministically-validated decision. Use when asked to "analyze", "get a signal for", or "what does the agent think about" a symbol.
---

# QuantX multi-agent analysis

Drive the agentic decision pipeline for a symbol end-to-end.

## When to use
The user wants an AI trading opinion on a symbol (e.g. "analyze BTCUSDT",
"what's the agent's read on ETHUSDT 1h"). This runs the **whole** specialist
graph, not a single prompt.

## How it works (so you can explain results)
`app/agents/orchestration/graph.py` wires a LangGraph `StateGraph`:

    init → market → technical → quant → risk → synthesis → [execute?]

- **init** captures a live reference price.
- **market / technical / quant** specialists each run the shared tool-calling
  loop (`AgentRunner`) with only their role's tools. The quant agent may call
  `predict_direction` (the ML model) and `run_backtest`.
- **risk** reads persisted risk state and sets a hard `halted` flag.
- **synthesis** emits one decision, re-checked by `AIDecisionValidator`; a halt,
  missing price, or failed check → `WAIT`.
- **execution** places a *paper* order only if mutations are enabled, the
  decision is actionable, and trading is not halted. Live trading is never
  reachable from the graph.

## Steps
1. Ensure the stack is up and candles are backfilled for the symbol/timeframe
   (the specialists read stored data).
2. Prefer the HTTP endpoint when the app is running:
   `POST /api/v1/agent/orchestrate?symbol=BTCUSDT` (auth required).
3. Or drive it in a REPL/script:
   ```python
   from app.agents.llm import build_provider
   from app.agents.orchestration import build_orchestrator
   from app.agents.tools.base import ToolContext
   orch = build_orchestrator(build_provider(), ToolContext(session=session, user_id=uid, client=client))
   state = await orch.run("BTCUSDT")
   print(state.final_decision, state.reports)
   ```
4. Report the decision AND the per-specialist summaries and `state.log`, so the
   reasoning chain is visible — not just the final action.

## Safety
Never weaken the risk gate or the mainnet interlock to force an actionable
decision. `WAIT` is a correct outcome, not a failure.
