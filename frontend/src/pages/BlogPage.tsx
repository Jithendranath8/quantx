import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, ArrowUpRight, CheckCircle2, Github, Globe } from 'lucide-react';

import { LogoMark } from '../components/brand/Logo';
import { SequenceDiagram } from '../components/blog/SequenceDiagram';
import type { SequenceParticipant, SequenceStep } from '../components/blog/SequenceDiagram';
import {
  AgentGraphDiagram, ArchitectureDiagram, BackendLayers, DataModelDiagram, DecisionPipeline, MarketDataPath,
} from '../components/blog/diagrams';
import { Callout, CodeBlock, Details, Figure, Screenshot, TableOfContents } from '../components/blog/primitives';
import type { TocEntry } from '../components/blog/primitives';
import { GridBackdrop, Spotlight } from '../components/fx/effects';
import { WORKSPACES } from '../lib/navigation';

// Every technical statement on this page was checked against the code at
// commit 5f1fb3a (23 Nov 2026). Numbers come from the code or from a real
// local run on that date; anything illustrative is labelled as such.
//
// Writing rule for this page: the main text is for a first-time reader.
// Anything deeper goes inside a <Details> box, which is closed by default.

const LIVE_SITE = 'https://quantx-dpu.pages.dev';
const REPO = 'https://github.com/Jithendranath8/quantx';

const TOC: TocEntry[] = [
  {
    id: 'problem',
    label: 'Problem statement',
    children: [
      { id: 'problem-audience', label: 'Who it is for' },
      { id: 'problem-terms', label: 'Key terms' },
    ],
  },
  { id: 'objectives', label: 'Objectives' },
  {
    id: 'tour',
    label: 'A quick tour',
    children: [
      { id: 'tour-signin', label: 'Signing in' },
      { id: 'tour-first', label: 'A first session' },
    ],
  },
  { id: 'tech', label: 'Technologies used' },
  {
    id: 'implementation',
    label: 'Implementation approach',
    children: [
      { id: 'impl-overview', label: 'System overview' },
      { id: 'impl-data', label: 'How data is stored' },
      { id: 'impl-agents', label: 'Feature 1: AI decisions' },
      { id: 'impl-paper', label: 'Feature 2: Paper trading' },
      { id: 'impl-decisions', label: 'Design decisions' },
    ],
  },
  {
    id: 'outcomes',
    label: 'Key outcomes',
    children: [
      { id: 'outcomes-works', label: 'What works today' },
      { id: 'outcomes-proof', label: 'Results from real runs' },
      { id: 'outcomes-testing', label: 'Testing and quality' },
      { id: 'outcomes-lessons', label: 'Lessons learned' },
    ],
  },
  { id: 'limitations', label: 'Limitations' },
  {
    id: 'try',
    label: 'Try it yourself',
    children: [
      { id: 'try-live', label: 'The live site' },
      { id: 'try-local', label: 'Run it locally' },
      { id: 'try-api', label: 'Call the API' },
    ],
  },
];

const TERMS: [string, string][] = [
  ['Paper trading', 'Practice trading with play money, using real market prices.'],
  ['Backtest', 'Replaying a strategy on past prices to see how it would have done.'],
  ['Stop-loss / target', 'Prices at which a trade closes, to cap a loss or take a profit.'],
  ['Risk-to-reward', 'How much a trade could gain for each unit it could lose.'],
  ['LLM', 'A large language model, such as Claude or GPT.'],
  ['AI agent', 'An LLM that can call tools (small functions) to look up real data before it answers.'],
  ['Validator', 'Plain code in QuantX that re-checks the numbers an AI gives.'],
  ['Testnet', 'Binance’s practice exchange. The real one is called mainnet.'],
];

const OBJECTIVES: { title: string; body: string }[] = [
  { title: 'Bring market data into one place', body: 'Live Binance prices, charts with indicators, the order book, and stored price history.' },
  { title: 'Let people test ideas safely', body: 'Paper trading with realistic fees and slippage, plus backtests on stored history.' },
  { title: 'Use AI agents for analysis', body: 'Specialist agents that study a market and suggest a trade, with any AI provider — even a free local model.' },
  { title: 'Make AI mistakes harmless', body: 'Re-check every AI answer with plain code, enforce risk limits, and keep real-money trading out of the AI’s reach.' },
  { title: 'Make results traceable', body: 'Store each AI decision with its cost and check result, and tie research runs to the exact data used.' },
  { title: 'Build it to a professional standard', body: 'Automated tests against real databases, continuous integration, a security review, and a one-command Docker setup.' },
];

const TECH: { group: string; items: [string, string][] }[] = [
  {
    group: 'Frontend',
    items: [
      ['React 18 + TypeScript', 'The web app: a public home page, this blog, and 17 app pages'],
      ['Vite 6', 'Builds and serves the frontend'],
      ['Tailwind CSS + DaisyUI', 'Styling and UI components'],
      ['lightweight-charts', 'Candlestick and indicator charts'],
    ],
  },
  {
    group: 'Backend',
    items: [
      ['Python 3.13 + FastAPI', 'The REST API (67 operations) and the WebSocket server'],
      ['SQLAlchemy 2 + Alembic', 'Database access and versioned schema changes'],
      ['Pydantic', 'Checks every input — including arguments the AI sends to tools'],
      ['Celery', 'Scheduled background jobs'],
    ],
  },
  {
    group: 'Data',
    items: [
      ['PostgreSQL 16', 'Permanent storage: users, prices, orders, AI decisions'],
      ['Redis 7 (two instances)', 'One for cache, live prices and locks; one as the job queue'],
      ['Binance API', 'Market data, and orders on the testnet'],
    ],
  },
  {
    group: 'AI',
    items: [
      ['LangGraph', 'Runs the four specialist agents as a step-by-step graph'],
      ['Anthropic + OpenAI SDKs', 'Talk to Claude, OpenAI, Groq, Gemini or a local Ollama model'],
      ['Model Context Protocol (MCP)', 'Lets tools like Claude Code use QuantX’s functions'],
      ['PyTorch / TensorFlow + MLflow', 'Optional price-direction model and experiment tracking'],
    ],
  },
  {
    group: 'Delivery',
    items: [
      ['Docker Compose + nginx', 'Runs the whole system with one command'],
      ['GitHub Actions', 'Tests, builds and security checks on every push to main'],
      ['Prometheus + Grafana', 'Metrics collection'],
    ],
  },
];

const DESIGN_DECISIONS: { title: string; body: string }[] = [
  {
    title: 'Plain code has the final say',
    body: 'Models are unreliable with numbers, so every number is re-checked. A weak model then fails safely, as WAIT, instead of making a confident mistake.',
  },
  {
    title: 'One set of tools for every AI provider',
    body: 'Each tool is defined once and translated for OpenAI, Anthropic and MCP, so the three can never drift apart.',
  },
  {
    title: 'Any AI provider, even a free local one',
    body: 'Set an Anthropic key, or point QuantX at any OpenAI-compatible service, including Ollama on your own computer. No paid account is needed.',
  },
  {
    title: 'Two Redis instances',
    body: 'The cache is allowed to throw data away when it is full. The job queue must never do that, or scheduled jobs would silently disappear.',
  },
  {
    title: 'Never hold the database while waiting on the network',
    body: 'An agent run can take minutes. Database connections are released before every AI call, so one slow run cannot block other users.',
  },
  {
    title: 'Real orders are saved first and sent once',
    body: 'If the network fails mid-order, the order is looked up by its own ID instead of being sent again — a retry could buy twice.',
  },
];

const WORKS_TODAY: string[] = [
  'Sign-up with email and password, or Google / GitHub when configured',
  'Live Binance prices, candlestick charts with indicators, and the order book',
  'Paper trading with market, limit, stop-loss and take-profit orders',
  'Backtests, walk-forward tests, parameter search and Monte Carlo simulation',
  'An AI Agent page, and the four-agent graph over the API',
  'A risk engine and circuit breaker the AI cannot override',
  'Live trading on Binance’s testnet, behind two settings and a per-user permission',
  'An MCP server, Docker Compose setup and a CI pipeline',
];

const NUMBERS: [string, string][] = [
  ['67', 'HTTP API operations'],
  ['17', 'app pages'],
  ['11', 'tools the AI can call'],
  ['5', 'built-in strategies'],
  ['669', 'automated tests passing'],
  ['10', 'database migrations'],
  ['14', 'security issues found and fixed'],
  ['$0', 'AI cost with a local model'],
];

const LIMITATIONS: ReactNode[] = [
  <>The four-agent graph has no screen yet. It runs through the API only, and its decisions are not saved to the AI log.</>,
  <>When the graph places a paper order, it uses a fixed small size (0.001), not a size based on the decision.</>,
  <>Only Binance spot trading is supported — no futures.</>,
  <>Paper trading can buy and then sell, but cannot short-sell. There are no OCO orders or partial fills.</>,
  <>Stop-loss and target prices on live orders are saved, but not placed on the exchange.</>,
  <>The Event Ledger page records live orders and kill-switch use only — not paper orders or AI decisions.</>,
  <>The AI “win rate” is a simulated check against later prices, not real profit.</>,
  <>The AI is never given news; there is no news feed.</>,
  <>Only the Market Data page updates live. Other pages refresh when you open them.</>,
  <>Small local models often give unusable answers, so most of their decisions end as WAIT.</>,
  <>The optional ML model must be trained locally and is not part of the cloud setup.</>,
  <>Money is stored as floating-point numbers — fine for a simulator, not for a real ledger. There are no frontend unit tests.</>,
];

const ORCHESTRATE_PARTICIPANTS: SequenceParticipant[] = [
  { id: 'client', label: 'Client', sub: 'any HTTP client' },
  { id: 'api', label: 'API route', sub: 'orchestrator.py' },
  { id: 'graph', label: 'Graph', sub: 'LangGraph' },
  { id: 'runner', label: 'AgentRunner', sub: 'tool loop' },
  { id: 'tools', label: 'Tool registry', sub: '11 tools' },
  { id: 'llm', label: 'LLM', sub: 'any provider' },
  { id: 'validator', label: 'Validator', sub: 'validator.py' },
];

const ORCHESTRATE_STEPS: SequenceStep[] = [
  { kind: 'msg', from: 'client', to: 'api', label: 'POST /agent/orchestrate?symbol=BTCUSDT' },
  { kind: 'note', over: ['api'], text: 'sign-in · 10/min · 2 runs · 240 s', tone: 'gate' },
  { kind: 'msg', from: 'api', to: 'graph', label: 'run(symbol) + ToolContext' },
  { kind: 'msg', from: 'graph', to: 'tools', label: 'init: get_price' },
  { kind: 'msg', from: 'tools', to: 'graph', label: 'reference price', reply: true },
  { kind: 'note', over: ['graph', 'llm'], text: 'repeat for each specialist: market → technical → quant → risk', tone: 'loop' },
  { kind: 'msg', from: 'graph', to: 'runner', label: 'role prompt + role tools' },
  { kind: 'msg', from: 'runner', to: 'llm', label: 'chat(messages, tool specs)' },
  { kind: 'msg', from: 'llm', to: 'runner', label: 'tool calls', reply: true },
  { kind: 'msg', from: 'runner', to: 'tools', label: 'validated call' },
  { kind: 'msg', from: 'tools', to: 'runner', label: '{ok, data | error}', reply: true },
  { kind: 'msg', from: 'runner', to: 'graph', label: 'report (≤ 8 rounds)', reply: true },
  { kind: 'msg', from: 'graph', to: 'tools', label: 'get_risk_state → halted? (fail closed)' },
  { kind: 'msg', from: 'graph', to: 'llm', label: 'synthesis prompt, no tools' },
  { kind: 'msg', from: 'llm', to: 'graph', label: 'decision JSON', reply: true },
  { kind: 'msg', from: 'graph', to: 'validator', label: 'validate(decision, price, balance)' },
  { kind: 'msg', from: 'validator', to: 'graph', label: 'valid, or reasons', reply: true },
  { kind: 'note', over: ['graph', 'validator'], text: 'unparseable · halted · no price · invalid  →  WAIT', tone: 'gate' },
  { kind: 'msg', from: 'graph', to: 'tools', label: 'submit_paper_order (only if allowed)', optional: true },
  { kind: 'msg', from: 'graph', to: 'api', label: 'final state', reply: true },
  { kind: 'msg', from: 'api', to: 'client', label: 'decision · reports · log', reply: true },
];

const PAPER_PARTICIPANTS: SequenceParticipant[] = [
  { id: 'browser', label: 'Browser', sub: 'Paper Trading' },
  { id: 'api', label: 'API route', sub: 'POST /paper/orders' },
  { id: 'svc', label: 'PaperTrading', sub: 'service' },
  { id: 'db', label: 'PostgreSQL', sub: 'accounts · orders' },
  { id: 'binance', label: 'Binance', sub: 'get_price' },
  { id: 'risk', label: 'RiskManager', sub: 'pure engine' },
];

const PAPER_STEPS: SequenceStep[] = [
  { kind: 'msg', from: 'browser', to: 'api', label: '{account_id, symbol, side, quantity}' },
  { kind: 'note', over: ['api'], text: 'sign-in · 60/min · bounded input', tone: 'gate' },
  { kind: 'msg', from: 'api', to: 'svc', label: 'submit_order(user, request)' },
  { kind: 'msg', from: 'svc', to: 'db', label: 'SELECT account … FOR UPDATE' },
  { kind: 'msg', from: 'svc', to: 'binance', label: 'current price' },
  { kind: 'msg', from: 'binance', to: 'svc', label: 'last price', reply: true },
  { kind: 'msg', from: 'svc', to: 'svc', label: 'fill = price × 1.0005 · fee 0.075%' },
  { kind: 'msg', from: 'svc', to: 'db', label: 'open positions · today’s loss' },
  { kind: 'msg', from: 'svc', to: 'risk', label: 'validate_trade(equity, exposure, size)' },
  { kind: 'msg', from: 'risk', to: 'svc', label: 'approved + size, or reason', reply: true },
  { kind: 'note', over: ['svc', 'risk'], text: 'rejected or oversized  →  400, nothing written', tone: 'gate' },
  { kind: 'msg', from: 'svc', to: 'db', label: 'balance, position, order · COMMIT' },
  { kind: 'msg', from: 'api', to: 'browser', label: '201 Created + order', reply: true },
];

// ── code and API samples ──────────────────────────────────────────────

const VALIDATOR_SNIPPET = `# backend/app/agents/validator.py (excerpt)

# 2. Price sanity: the stop must be on the losing side of entry and the
#    target on the winning side, for the stated direction.
if decision.action == "BUY":
    if stop_loss >= entry:
        rejections.append(f"Impossible SL direction for BUY: SL ({stop_loss}) >= Entry ({entry})")
    if take_profit <= entry:
        rejections.append(f"Impossible TP direction for BUY: TP ({take_profit}) <= Entry ({entry})")
elif decision.action == "SELL":
    if stop_loss <= entry:
        rejections.append(f"Impossible SL direction for SELL: SL ({stop_loss}) <= Entry ({entry})")
    if take_profit >= entry:
        rejections.append(f"Impossible TP direction for SELL: TP ({take_profit}) >= Entry ({entry})")

# 3. Authoritative risk:reward, recomputed from the model's own prices.
risk = abs(entry - stop_loss)
reward = abs(take_profit - entry)
calculated_rr = (reward / risk) if risk > 0 else 0.0`;

const ROUTE_SNIPPET = `# backend/app/agents/orchestration/graph.py (excerpt)

def _route_after_synthesis(self, state: OrchestrationState) -> str:
    decision = state.final_decision or {}
    actionable = decision.get("action") in {"BUY", "SELL"}
    if self._ctx.allow_mutations and actionable and not state.halted:
        return "execute"
    return "end"`;

const RISK_SNIPPET = `# backend/app/engines/risk/manager.py (excerpt)

# 5. Portfolio Exposure Check
max_exposure_usd = request.account_balance * self.config.max_portfolio_exposure_pct
new_exposure_usd = request.current_exposure_usd + request.order_amount_usd
if new_exposure_usd > max_exposure_usd:`;

const ORCHESTRATE_RESPONSE = `{
  "symbol": "BTCUSDT",
  "decision": {
    "action": "WAIT",
    "confidence": 0.0,
    "reasoning": "Unparseable synthesis: 1 validation error for AgentDecision\\naction\\n  Input should be 'BUY', 'SELL' or 'WAIT' [type=literal_error, input_value=None, …]",
    "entry_price": null,
    "stop_loss": null,
    "take_profit": null,
    "invalidation_level": null,
    "risk_reward_ratio": null
  },
  "reports": {
    "market": "The current live price for BTCUSDT is $63,751.01. In the last hour, the market has shown a range-bound behavior … (trimmed)",
    "technical": "The multi-timeframe snapshot for BTCUSDT shows a bullish posture in the short-term (1m timeframe) … (trimmed)",
    "quant": "The available strategies for BTCUSDT are: EMA Crossover … Next, I will run a backtest … (trimmed)",
    "risk": "… Halted: No … No binding limits are currently in place for this trade … (trimmed)"
  },
  "halted": false,
  "market_price": 63715.61,
  "executed_order": null,
  "log": [
    "init: price=63715.61",
    "market: 2 tool call(s)",
    "technical: 1 tool call(s)",
    "quant: 1 tool call(s)",
    "risk: 1 tool call(s)",
    "synthesis: WAIT"
  ]
}`;

const PAPER_REQUEST = `curl -X POST http://localhost:8000/api/v1/paper/orders \\
  -H "Authorization: Bearer $TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
        "account_id": "d3c6feff-1915-415f-9d5c-3f50026f11e0",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": 0.05
      }'`;

const PAPER_RESPONSE = `HTTP/1.1 201 Created

{
  "id": "4ed765f1-3926-43da-b080-bc11e22b747c",
  "account_id": "d3c6feff-1915-415f-9d5c-3f50026f11e0",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "order_type": "MARKET",
  "quantity": 0.05,
  "price": 63733.03,
  "stop_price": null,
  "filled_price": 63764.89651499999,
  "filled_quantity": 0.05,
  "status": "FILLED",
  "stop_loss": null,
  "take_profit": null
}`;

const PAPER_REJECTED = `# Same request with "quantity": 0.5

HTTP/1.1 400 Bad Request

{
  "error": true,
  "message": "Paper order of $31,882.45 exceeds the risk-per-trade limit of $9,999.60 without a stop loss.",
  "details": { "rule": "risk_per_trade" }
}`;

const LOCAL_SETUP = `git clone ${REPO}.git && cd quantx
cp .env.example .env

# Generate the five required secrets, then paste them into .env
python3 -c "import secrets; [print(f'{k}={secrets.token_urlsafe(48)}') for k in ('SECRET_KEY','JWT_SECRET_KEY','POSTGRES_PASSWORD','REDIS_PASSWORD','GRAFANA_ADMIN_PASSWORD')]"

# Prometheus reads the metrics password from a file
grep '^SECRET_KEY=' .env | cut -d= -f2- | tr -d '\\n' > monitoring/prometheus/metrics_password

# Build and start everything; migrations run before the API starts
docker compose up -d --build`;

const OLLAMA_SETUP = `# A free local model (no API key, nothing leaves your machine)
brew install ollama && ollama serve &
ollama pull qwen2.5:3b

# in .env
OPENAI_BASE_URL=http://host.docker.internal:11434/v1
OPENAI_MODEL=qwen2.5:3b
OPENAI_API_KEY=`;

const API_WALKTHROUGH = `API=http://localhost:8000/api/v1

# 1. Create a user (password: 8+ characters), then sign in
curl -s -X POST $API/auth/register -H 'Content-Type: application/json' \\
  -d '{"email":"you@example.com","username":"you","password":"a-long-password"}'
TOKEN=$(curl -s -X POST $API/auth/login -H 'Content-Type: application/json' \\
  -d '{"email":"you@example.com","password":"a-long-password"}' \\
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["tokens"]["access_token"])')

# 2. Open a paper account with play money
curl -s -X POST $API/paper/accounts -H "Authorization: Bearer $TOKEN" \\
  -H 'Content-Type: application/json' -d '{"name":"My paper account","initial_balance":100000}'

# 3. Ask the four specialists (needs a configured LLM; can take a minute)
curl -s -X POST "$API/agent/orchestrate?symbol=BTCUSDT" -H "Authorization: Bearer $TOKEN"
# add &execute=true to let a validated BUY or SELL place a paper order`;

// ── small building blocks ─────────────────────────────────────────────

function Code({ children }: { children: ReactNode }) {
  return (
    <code className="rounded-md bg-white/[0.06] px-1.5 py-0.5 font-mono text-[0.86em] text-zinc-200 ring-1 ring-inset ring-white/[0.06] break-words">
      {children}
    </code>
  );
}

function P({ children }: { children: ReactNode }) {
  return <p className="mt-5 max-w-[66ch] text-[17px] leading-[1.75] text-zinc-300">{children}</p>;
}

function Strong({ children }: { children: ReactNode }) {
  return <strong className="font-medium text-white">{children}</strong>;
}

function H3({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h3 id={id} className="mt-14 scroll-mt-32 text-xl font-medium tracking-tight text-white sm:text-[1.45rem]">
      {children}
    </h3>
  );
}

function H4({ children }: { children: ReactNode }) {
  return <h4 className="mt-8 text-[15px] font-semibold uppercase tracking-[0.08em] text-zinc-400">{children}</h4>;
}

function Section({
  id,
  num,
  title,
  lead,
  children,
}: {
  id: string;
  num: number;
  title: ReactNode;
  /** One plain sentence saying what the section is about. */
  lead: string;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="border-t border-white/[0.06] pt-16 pb-6 first:border-t-0 first:pt-4">
      <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-brand-400">Section {String(num).padStart(2, '0')}</p>
      <h2 id={id} className="mt-3 scroll-mt-32 font-display text-[clamp(2.1rem,4.2vw,3.1rem)] leading-[1.04] text-white">
        {title}
      </h2>
      <p className="mt-4 max-w-[60ch] text-lg leading-relaxed text-zinc-400">{lead}</p>
      {children}
    </section>
  );
}

function Bullets({ items }: { items: ReactNode[] }) {
  return (
    <ul className="mt-5 max-w-[66ch] space-y-3">
      {items.map((item, i) => (
        <li key={i} className="flex gap-3 text-[16.5px] leading-[1.7] text-zinc-300">
          <span className="mt-[0.72em] h-1 w-1 shrink-0 rounded-full bg-brand-400" />
          <span className="min-w-0">{item}</span>
        </li>
      ))}
    </ul>
  );
}

function Steps({ items }: { items: { title: string; body: ReactNode }[] }) {
  return (
    <ol className="mt-6 space-y-3">
      {items.map((item, i) => (
        <li key={item.title} className="grid grid-cols-[2.25rem_minmax(0,1fr)] gap-3 rounded-2xl border border-white/[0.06] bg-ink-900/50 p-4 sm:p-5">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-500/10 font-mono text-xs text-brand-300 ring-1 ring-inset ring-brand-500/25">
            {i + 1}
          </span>
          <div className="min-w-0">
            <p className="text-[15.5px] font-medium text-white">{item.title}</p>
            <div className="mt-1 text-[15px] leading-relaxed text-zinc-400">{item.body}</div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-ink-950/85 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-[1240px] items-center gap-3 px-4 sm:px-6">
        {/* A full page load: the landing page is served with its own CSP. */}
        <a href="/" className="flex items-center gap-2.5 cursor-pointer" aria-label="QuantX home">
          <LogoMark />
          <span className="hidden text-[15px] font-semibold tracking-tight text-white sm:inline">
            Quant<span className="text-brand-400">X</span>
          </span>
        </a>
        <span className="text-zinc-700" aria-hidden="true">/</span>
        <span className="text-sm text-zinc-300">Blog</span>
        <nav aria-label="Project links" className="ml-auto flex items-center gap-1 sm:gap-2">
          <a
            href={REPO}
            target="_blank"
            rel="noreferrer"
            aria-label="Source code on GitHub"
            className="inline-flex h-9 items-center gap-1.5 rounded-full px-3 text-sm text-zinc-400 transition-colors hover:text-white cursor-pointer"
          >
            <Github className="h-4 w-4" />
            <span className="hidden sm:inline">Source</span>
          </a>
          <Link
            to="/app"
            className="inline-flex h-9 items-center gap-1.5 rounded-full bg-white px-4 text-sm font-medium text-ink-950 transition hover:bg-zinc-200 cursor-pointer"
          >
            Open the app <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </nav>
      </div>
    </header>
  );
}

function Hero() {
  const facts: [string, string][] = [
    ['67', 'API operations'],
    ['17', 'app pages'],
    ['11', 'AI tools'],
    ['669', 'tests passing'],
  ];
  return (
    <section className="relative overflow-hidden border-b border-white/[0.06]">
      <Spotlight className="-top-40 left-0 md:-top-24 md:left-32" />
      <GridBackdrop />
      <div className="relative mx-auto max-w-[1240px] px-4 pb-14 pt-14 sm:px-6 lg:pb-20 lg:pt-20">
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-brand-400">
          Project write-up · 23 November 2026 · 12-minute read
        </p>
        <h1 className="mt-5 max-w-4xl font-display text-[clamp(2.6rem,6vw,4.8rem)] leading-[1] tracking-tight text-white">
          QuantX: AI agents suggest trades. <em className="text-brand-400">Plain math decides.</em>
        </h1>
        <p className="mt-6 max-w-2xl text-[17px] leading-relaxed text-zinc-400 sm:text-lg">
          QuantX is a web app for studying crypto markets without risking real money. It shows live prices, lets you
          test trading strategies on past data, and asks a team of AI agents for trade ideas. Every AI idea is then
          checked by ordinary code and strict risk limits — and by default, any trade uses play money.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <a
            href={LIVE_SITE}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-10 items-center gap-2 rounded-full bg-white px-5 text-sm font-medium text-ink-950 transition hover:bg-zinc-200 cursor-pointer"
          >
            <Globe className="h-4 w-4" /> Live site <ArrowUpRight className="h-3.5 w-3.5" />
          </a>
          <a
            href={REPO}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-10 items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-5 text-sm text-zinc-200 transition hover:border-white/20 hover:bg-white/[0.06] cursor-pointer"
          >
            <Github className="h-4 w-4" /> Source on GitHub <ArrowUpRight className="h-3.5 w-3.5" />
          </a>
          <a href="#try" className="text-sm text-zinc-400 transition-colors hover:text-white cursor-pointer">
            Run it yourself →
          </a>
        </div>
        <dl className="mt-12 grid max-w-3xl grid-cols-2 gap-x-6 gap-y-6 border-t border-white/[0.07] pt-6 sm:grid-cols-4">
          {facts.map(([value, label]) => (
            <div key={label} className="flex flex-col-reverse">
              <dt className="mt-1 text-xs text-zinc-500">{label}</dt>
              <dd className="font-mono text-2xl text-white">{value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

function InShort() {
  const rows: [string, string][] = [
    ['What', 'A research platform for crypto markets, using live data from the Binance exchange.'],
    ['The idea', 'AI agents may suggest trades, but only plain code and risk rules decide. The AI can never reach real money.'],
    ['Built with', 'React, FastAPI, PostgreSQL, Redis and LangGraph, packaged with Docker.'],
    ['Result', 'Works end to end on a local machine, with 669 automated tests passing.'],
  ];
  return (
    <div className="mt-8 overflow-hidden rounded-2xl border border-brand-500/20 bg-brand-500/[0.04]">
      <p className="border-b border-white/[0.06] px-5 py-3 font-mono text-[11px] uppercase tracking-[0.18em] text-brand-300">
        In 30 seconds
      </p>
      <dl className="divide-y divide-white/[0.05]">
        {rows.map(([k, v]) => (
          <div key={k} className="grid gap-1 px-5 py-3 sm:grid-cols-[110px_minmax(0,1fr)] sm:gap-4">
            <dt className="text-sm font-medium text-white">{k}</dt>
            <dd className="text-[15px] leading-relaxed text-zinc-300">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

// ── the page ──────────────────────────────────────────────────────────

export default function BlogPage() {
  useEffect(() => {
    document.title = 'How QuantX works — QuantX Blog';
    // The page is loaded on demand, so the browser's own jump to #section can
    // happen before the section exists. Repeat it once the page has rendered.
    const hash = window.location.hash.slice(1);
    if (hash) document.getElementById(decodeURIComponent(hash))?.scrollIntoView();
  }, []);

  return (
    <div className="min-h-screen bg-ink-950">
      <a
        href="#article"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:text-ink-950"
      >
        Skip to the article
      </a>
      <SiteHeader />
      <Hero />

      <div className="mx-auto max-w-[1240px] px-4 sm:px-6 lg:grid lg:grid-cols-[230px_minmax(0,1fr)] lg:gap-14">
        <TableOfContents entries={TOC} />

        <main id="article" className="min-w-0 pb-24 pt-6 lg:pt-14">
          {/* ── 1 Problem ─────────────────────────────────────── */}
          <Section
            id="problem"
            num={1}
            title="Problem statement"
            lead="How can you use AI’s ideas about the market without letting AI’s mistakes cost money?"
          >
            <InShort />
            <P>
              AI language models are good at reading a lot of information and explaining it clearly. But they are
              unreliable with numbers, and they sound just as confident when they are wrong. A model might put a stop-loss
              on the wrong side of the price, or claim a risk-to-reward ratio that its own numbers do not support.
            </P>
            <P>
              In most apps a wrong answer is just annoying. In trading, it loses money. QuantX answers this with one simple
              rule: <Strong>the AI may suggest; only plain code and explicit settings may decide.</Strong>
            </P>
            <Figure kind="Diagram" caption="The path every AI suggestion takes in QuantX.">
              <DecisionPipeline />
            </Figure>

            <H3 id="problem-audience">Who it is for</H3>
            <Bullets
              items={[
                <><Strong>Students and beginners</Strong> who want to learn how markets behave, using real prices and play money.</>,
                <><Strong>Researchers</Strong> who want to test a strategy on past data before trusting it.</>,
                <><Strong>Developers</Strong> curious about how to give AI agents real tools without giving them real power.</>,
              ]}
            />

            <H3 id="problem-terms">Key terms</H3>
            <P>A few words come up often. Here is what they mean:</P>
            <dl className="mt-6 grid gap-3 sm:grid-cols-2">
              {TERMS.map(([term, meaning]) => (
                <div key={term} className="rounded-2xl border border-white/[0.07] bg-ink-900/50 px-4 py-3">
                  <dt className="text-sm font-medium text-white">{term}</dt>
                  <dd className="mt-1 text-sm leading-relaxed text-zinc-400">{meaning}</dd>
                </div>
              ))}
            </dl>
          </Section>

          {/* ── 2 Objectives ──────────────────────────────────── */}
          <Section
            id="objectives"
            num={2}
            title="Objectives"
            lead="The project set out to do six things. All six are in the current code; section 6 shows the evidence."
          >
            <ol className="mt-8 grid gap-3 md:grid-cols-2">
              {OBJECTIVES.map((o, i) => (
                <li key={o.title} className="flex gap-4 rounded-2xl border border-white/[0.07] bg-ink-900/60 p-5">
                  <span className="font-display text-3xl leading-none text-brand-400">{i + 1}</span>
                  <div className="min-w-0">
                    <p className="text-[15.5px] font-medium text-white">{o.title}</p>
                    <p className="mt-1.5 text-sm leading-relaxed text-zinc-400">{o.body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </Section>

          {/* ── 3 Tour ────────────────────────────────────────── */}
          <Section
            id="tour"
            num={3}
            title="A quick tour"
            lead="What a new user sees, from signing up to testing a first idea. All screenshots are from the real app, run locally on 23 November 2026."
          >
            <H3 id="tour-signin">Signing in and finding your way</H3>
            <P>
              You sign up with an email and password, or with Google or GitHub. Inside the app, the 17 pages are grouped
              into five <Strong>workspaces</Strong>, each answering one question, so you only see what matters for the task
              at hand. Pressing <Code>⌘K</Code> (or <Code>Ctrl K</Code>) opens a search box that jumps to any page.
            </P>
            <div className="mt-6 overflow-hidden rounded-2xl border border-white/[0.08]">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">The five workspaces and their pages</caption>
                <thead className="bg-ink-850/80 text-[11px] uppercase tracking-wider text-zinc-500">
                  <tr>
                    <th scope="col" className="px-4 py-2.5 font-semibold">Workspace</th>
                    <th scope="col" className="hidden px-4 py-2.5 font-semibold sm:table-cell">Question</th>
                    <th scope="col" className="px-4 py-2.5 font-semibold">Pages</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.05] bg-ink-900/50">
                  {WORKSPACES.map((w) => (
                    <tr key={w.id} className="align-top">
                      <th scope="row" className="px-4 py-3 font-medium text-white">
                        {w.label}
                        <span className="mt-1 block font-display text-[15px] font-normal italic text-brand-300/90 sm:hidden">
                          {w.question}
                        </span>
                      </th>
                      <td className="hidden px-4 py-3 font-display text-[15px] italic text-brand-300/90 sm:table-cell">{w.question}</td>
                      <td className="px-4 py-3 text-zinc-400">{w.pages.map((p) => p.label).join(' · ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <H3 id="tour-first">A first session</H3>
            <P>
              The dashboard shows a four-step checklist and ticks each step off as you do it: look at a market, fund a
              paper account, ask the AI agent, and backtest a strategy.
            </P>
            <Screenshot
              src="/images/blog/dashboard.webp"
              alt="QuantX dashboard greeting the user, showing the four-step first-session checklist with step two done, and tiles for total equity $99,997.61, unrealized PnL, win rate and one open position."
              caption="The dashboard after one paper order: account value, cash, open positions, and the first-session checklist."
            />
            <Screenshot
              src="/images/blog/market-chart.webp"
              alt="Market Data page showing a 15-minute BTCUSDT candlestick chart with moving averages, volume, MACD and RSI panes, beside a live order book of bids and asks."
              caption="Market Data: a 15-minute Bitcoin chart with moving averages, volume, MACD and RSI, next to the live order book."
            />
            <Screenshot
              src="/images/blog/agent.webp"
              alt="AI Trading Agent page showing a WAIT decision with zero confidence; a banner says the validator overruled the model because its numbers did not add up, and the reasoning says the stop-loss and take-profit were missing."
              caption="The AI Agent page. A small local AI model suggested a trade with no stop-loss or target, so the validator turned it into WAIT. It took 36 seconds and cost $0."
            />
            <Screenshot
              src="/images/blog/backtest.webp"
              alt="Backtesting results for the EMA crossover strategy on BTCUSDT 1h: total return minus 57.57 percent, Sharpe minus 3.25, max drawdown 61.29 percent, win rate 30.90 percent over 398 trades, with a falling equity curve and a warning that the strategy lost money."
              caption="Backtesting: a simple moving-average strategy would have lost 57.6% over 398 trades. The page says so plainly rather than hiding it."
            />
          </Section>

          {/* ── 4 Technologies ────────────────────────────────── */}
          <Section
            id="tech"
            num={4}
            title="Technologies used"
            lead="Each tool was chosen for a specific job. Here is what does what."
          >
            <div className="mt-8 grid gap-4 md:grid-cols-2">
              {TECH.map((g) => (
                <div key={g.group} className="rounded-2xl border border-white/[0.07] bg-ink-900/60 p-5">
                  <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-brand-400">{g.group}</p>
                  <dl className="mt-3 space-y-3">
                    {g.items.map(([tech, use]) => (
                      <div key={tech}>
                        <dt className="text-[15px] font-medium text-white">{tech}</dt>
                        <dd className="text-sm leading-relaxed text-zinc-400">{use}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ))}
            </div>
          </Section>

          {/* ── 5 Implementation ──────────────────────────────── */}
          <Section
            id="implementation"
            num={5}
            title="Implementation approach"
            lead="How QuantX is built, from the big picture down to its two most important features."
          >
            <Callout title="How to read this section">
              The main text explains each part in plain words. The boxes marked <Strong>Technical details</Strong> hold the
              deeper version — open them if you want it, or skip them.
            </Callout>

            <H3 id="impl-overview">5.1 System overview</H3>
            <Figure
              kind="Diagram"
              scroll
              caption="System architecture, drawn from the project’s docker-compose.yml and backend code. Dashed boxes are outside services."
            >
              <ArchitectureDiagram />
            </Figure>
            <Bullets
              items={[
                <><Strong>The browser</Strong> runs the React app. It only ever talks to the API — never directly to the database, Binance or the AI.</>,
                <><Strong>The API</Strong> (FastAPI) handles every request and runs the AI agents. It runs as several processes at once, so shared things like live prices live in Redis.</>,
                <><Strong>PostgreSQL</Strong> stores everything permanent: users, price history, orders and AI decisions.</>,
                <><Strong>Redis</Strong> runs twice: one copy for fast shared data (cache, live prices, locks) and one as a job queue. They are separate because the queue must never lose a job.</>,
                <><Strong>Celery</Strong> runs scheduled jobs: filling waiting orders every minute, topping up prices every 10 minutes, and cleaning up old data every night.</>,
              ]}
            />
            <Details summary="Inside the backend, live prices, and where it runs">
              <H4>Backend layers</H4>
              <div className="mt-4">
                <BackendLayers />
              </div>
              <P>
                The core engines are pure: <Code>RiskManager.validate_trade</Code> takes numbers in and returns a decision,
                without reading the database. The service around it loads the real inputs and, on the live path, saves a
                tripped circuit breaker to the <Code>risk_state</Code> table, so the halt applies to every process and
                survives a restart.
              </P>
              <H4>Live prices</H4>
              <div className="mt-4">
                <MarketDataPath />
              </div>
              <P>
                Every API process runs the same start-up code, so without care each would open its own Binance connection.
                Instead, one process wins a Redis lock that expires after 30 seconds and is renewed every 10 seconds; if
                that process dies, another takes over. Only closed candles are stored. The live stream is off by default (
                <Code>MARKET_STREAM_ENABLED=false</Code>); the Market Data page then refreshes every 15 seconds.
              </P>
              <H4>Where it runs</H4>
              <P>
                Locally, one <Code>docker compose up</Code> starts the frontend (<Code>:5173</Code>), the API (
                <Code>:8000</Code>), PostgreSQL, both Redis copies, a migration step, Celery, Prometheus and Grafana. For a
                free cloud setup, the project’s DEPLOY.md uses Cloudflare Pages, Railway, Neon and Upstash, with a GitHub
                Actions schedule calling <Code>POST /api/v1/internal/jobs/{'{job}'}</Code> instead of an always-on worker.
              </P>
            </Details>

            <H3 id="impl-data">5.2 How data is stored</H3>
            <P>
              PostgreSQL holds four groups of data: <Strong>identity</Strong> (users and sign-in sessions),{' '}
              <Strong>paper trading</Strong> (play-money accounts, orders and positions), <Strong>live trading and risk</Strong>{' '}
              (real orders and each user’s risk state), and <Strong>market data, AI and research</Strong> (price candles, AI
              decisions and research runs). The schema is built by ten versioned migrations.
            </P>
            <Figure
              kind="Diagram"
              scroll
              caption="The main tables, grouped by purpose. Only a few columns of each are shown."
            >
              <DataModelDiagram />
            </Figure>
            <Details summary="Database rules and design choices">
              <Bullets
                items={[
                  <>The database itself enforces key rules: one row per candle (symbol + timeframe + time), at most one open position per account and coin, a unique ID for every live order, and one risk-state row per user.</>,
                  <>Only one foreign key is declared (<Code>refresh_tokens.user_id → users</Code>). Other links are plain IDs, and the service code checks on every request that a row belongs to the caller — which is why ownership has its own security tests.</>,
                  <>Live orders are written with their own ID <em>before</em> being sent to the exchange, so an interrupted request can always be traced.</>,
                  <>Each research run stores a SHA-256 fingerprint of the exact price data and the git commit, so a result can be checked later.</>,
                  <>Large tables (candles, event ledger, audit logs, AI decisions) are trimmed nightly by retention settings.</>,
                ]}
              />
            </Details>

            <H3 id="impl-agents">5.3 Feature 1: AI decisions that plain code checks</H3>
            <P>
              This is the most interesting part of QuantX. When you ask about a coin, <Strong>four specialist AI agents</Strong>{' '}
              each study one side of the market — market data, technical indicators, strategy tests, and risk. Each agent
              can only use its own <Strong>tools</Strong>: small functions that read real data. A final step combines their
              reports into one decision, and then plain code checks it.
            </P>
            <P>
              The app’s AI Agent page uses a simpler version: one AI call over data the backend prepares, followed by the
              same check. The four-agent version runs through the API (<Code>POST /api/v1/agent/orchestrate</Code>).
            </P>
            <Figure
              kind="Diagram"
              scroll
              caption="The four-agent graph. The names under each agent are exactly the tools it is allowed to use."
            >
              <AgentGraphDiagram />
            </Figure>
            <H4>Step by step</H4>
            <Steps
              items={[
                { title: 'Check the request', body: 'You must be signed in. Each user gets 10 runs a minute, 2 at a time, and a run stops after 240 seconds.' },
                { title: 'Get the real price first', body: 'Before any AI speaks, the system reads the current price, so the later check has a number it can trust.' },
                { title: 'Four specialists research', body: 'Market, technical, quant and risk agents run in turn. Each may call only its own tools, for at most 8 rounds.' },
                { title: 'Combine into one decision', body: 'A final AI call turns the four reports into BUY, SELL or WAIT, with an entry price, stop-loss and target.' },
                { title: 'Check it with plain code', body: 'If the answer is unreadable, trading is paused, or the numbers do not add up, the decision becomes WAIT.' },
                { title: 'Act only if allowed', body: 'A paper order is placed only if you asked for it, the decision is BUY or SELL, and trading is not paused. There is no tool for real orders at all.' },
              ]}
            />
            <H4>What the validator checks</H4>
            <Bullets
              items={[
                'A BUY or SELL must include a stop-loss and a target.',
                'Every price must be a real number above zero.',
                'The entry price must be within 10% of the real market price.',
                'For a BUY, the stop-loss must be below the entry and the target above it (the reverse for a SELL).',
                'The risk-to-reward ratio is recalculated. It must be at least 1 — and if the AI stated a ratio, the two must match closely.',
                'The trade size may not be more than 20% of the account.',
              ]}
            />
            <P>Here is the real code for the direction and risk-to-reward checks:</P>
            <CodeBlock label="Python · validator" code={VALIDATOR_SNIPPET} />
            <P>And this short function is the only place that decides whether the graph may place an order:</P>
            <CodeBlock label="Python · graph routing" code={ROUTE_SNIPPET} />
            <P>
              <Strong>A real run.</Strong> On 23 November 2026 the four-agent graph ran on a small, free local model
              (qwen2.5:3b). All four agents called their tools, but the model’s final answer had no action in it, so the
              check turned it into WAIT and nothing was traded. The risk agent had even written that “no binding limits
              are in place” — which is wrong, but harmless, because an AI’s words cannot change a limit.
            </P>
            <Details summary="Every message in order, and the raw response">
              <Figure
                kind="Diagram"
                scroll
                caption="One four-agent run as a sequence diagram, with messages numbered in order. The orange dashed arrow happens only when an order is allowed."
              >
                <SequenceDiagram
                  title="Sequence of one multi-agent orchestration run"
                  participants={ORCHESTRATE_PARTICIPANTS}
                  steps={ORCHESTRATE_STEPS}
                  colWidth={132}
                />
              </Figure>
              <Bullets
                items={[
                  <>Permissions live in a <Code>ToolContext</Code> the AI never sees. <Code>allow_mutations</Code> is simply the request’s <Code>execute</Code> flag, and defaults to false.</>,
                  <>Every tool call is validated by a Pydantic model first. A tool that changes anything refuses to run unless <Code>allow_mutations</Code> is true, and failures come back as readable errors, not crashes.</>,
                  <>The database transaction is closed after every tool call, so no connection is held while the AI thinks.</>,
                  <>The risk node reads the saved “halted” flag itself. If that read fails, the run behaves as halted (fail closed).</>,
                ]}
              />
              <CodeBlock label="Response · POST /api/v1/agent/orchestrate?symbol=BTCUSDT (real, trimmed)" code={ORCHESTRATE_RESPONSE} />
            </Details>

            <H3 id="impl-paper">5.4 Feature 2: Paper trading with a risk engine</H3>
            <P>
              Paper trading means practising with play money against real prices. Every buy — whether you click it or the
              AI graph places it — goes through the same service, and the server works out every risk number itself. A
              market order only says what to trade and how much.
            </P>
            <Steps
              items={[
                { title: 'Lock the account', body: 'So two orders sent at the same moment cannot both spend the same balance.' },
                { title: 'Use the real price, plus real costs', body: 'The price comes from Binance, not from you. The fill is 0.05% worse than the market (slippage) and a 0.075% fee is charged.' },
                { title: 'Check the risk limits', body: 'The risk engine looks at your whole account, not just this order (rules below).' },
                { title: 'Save everything, or nothing', body: 'If approved, the balance, position and order are saved together. If refused, nothing is saved.' },
              ]}
            />
            <H4>The risk rules</H4>
            <Bullets
              items={[
                'If the circuit breaker is on, every buy is refused.',
                'If today’s losses reach 5% of the account, buying stops for the day.',
                'After closing a coin at a loss, you cannot buy it again for 15 minutes.',
                'You can hold at most 5 positions, with at most 50% of the account invested.',
                'Each trade may risk at most 2% of the account. Without a stop-loss, that caps the order at 10% of the account.',
              ]}
            />
            <P>
              <Strong>A real example.</Strong> Here is an actual exchange with the API from the local run. A buy of 0.05
              Bitcoin is accepted:
            </P>
            <CodeBlock label="Request" code={PAPER_REQUEST} />
            <CodeBlock label="Response" code={PAPER_RESPONSE} />
            <P>
              You can check the math: the market price 63,733.03 × 1.0005 = 63,764.90, the fill price. A fee of $2.39 is
              added, and the cash balance drops from $100,000 to $96,809.36. Ten times that size is refused:
            </P>
            <CodeBlock label="Response · oversized order" code={PAPER_REJECTED} />
            <P>
              Without a stop-loss, the limit is 10% of the account (about $99,996), which is $9,999.60. The $31,882 order is
              refused before anything is saved.
            </P>
            <Details summary="Every message in order, the rule in code, and orders that wait">
              <Figure kind="Diagram" scroll caption="A market buy on a paper account, from the browser to the database.">
                <SequenceDiagram
                  title="Sequence of a paper market order passing the risk engine"
                  participants={PAPER_PARTICIPANTS}
                  steps={PAPER_STEPS}
                  colWidth={150}
                />
              </Figure>
              <CodeBlock label="Python · risk manager" code={RISK_SNIPPET} />
              <P>
                Limit, stop-loss and take-profit orders wait as PENDING (at most 50 per account) and do not touch the
                balance yet. A job checks them every 60 seconds; when a buy triggers, the balance and the risk engine are
                checked again, because nothing was reserved earlier. The risk engine also refuses more than 10× leverage.
              </P>
            </Details>

            <H3 id="impl-decisions">5.5 Key design decisions</H3>
            <div className="mt-6 grid gap-3 md:grid-cols-2">
              {DESIGN_DECISIONS.map((d, i) => (
                <div key={d.title} className="rounded-2xl border border-white/[0.07] bg-ink-900/60 p-5">
                  <p className="font-mono text-xs text-brand-400">{String(i + 1).padStart(2, '0')}</p>
                  <p className="mt-2 text-[15.5px] font-medium text-white">{d.title}</p>
                  <p className="mt-2 text-sm leading-relaxed text-zinc-400">{d.body}</p>
                </div>
              ))}
            </div>
          </Section>

          {/* ── 6 Outcomes ────────────────────────────────────── */}
          <Section
            id="outcomes"
            num={6}
            title="Key outcomes"
            lead="What the project delivered, the evidence for it, and what building it taught."
          >
            <H3 id="outcomes-works">What works today</H3>
            <ul className="mt-6 grid gap-2.5 sm:grid-cols-2">
              {WORKS_TODAY.map((item) => (
                <li key={item} className="flex gap-3 rounded-xl border border-white/[0.06] bg-ink-900/50 px-4 py-3 text-sm leading-relaxed text-zinc-300">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <dl className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {NUMBERS.map(([value, label]) => (
                <div key={label} className="flex flex-col-reverse rounded-2xl border border-white/[0.07] bg-ink-900/60 p-4">
                  <dt className="mt-1 text-xs leading-snug text-zinc-500">{label}</dt>
                  <dd className="font-mono text-2xl text-white">{value}</dd>
                </div>
              ))}
            </dl>

            <H3 id="outcomes-proof">Results from real runs</H3>
            <P>The safety checks were not just tested in theory. On 23 November 2026, in a local run:</P>
            <div className="mt-6 grid gap-3 md:grid-cols-3">
              {[
                ['The validator overruled the AI', 'A small local model suggested a trade with no stop-loss or target. It was turned into WAIT.'],
                ['Bad output became WAIT', 'In a four-agent run, the final answer had no action. The check turned it into WAIT; no order was placed.'],
                ['An oversized order was refused', 'A $31,882 paper buy was refused, because the limit without a stop-loss was $9,999.60.'],
              ].map(([title, body]) => (
                <div key={title} className="rounded-2xl border border-emerald-500/20 bg-emerald-500/[0.04] p-5">
                  <p className="text-[15px] font-medium text-white">{title}</p>
                  <p className="mt-2 text-sm leading-relaxed text-zinc-400">{body}</p>
                </div>
              ))}
            </div>

            <H3 id="outcomes-testing">Testing and quality</H3>
            <P>
              <Strong>669 automated tests pass</Strong> (one more is skipped because it needs PyTorch, which the test setup
              leaves out). They run against real PostgreSQL and Redis databases in Docker, not stand-ins, so they test the
              same behaviour as production.
            </P>
            <Bullets
              items={[
                <>A <Strong>fake AI provider</Strong> drives the four-agent graph in tests, to prove that a bad decision becomes WAIT and that no order is placed without permission.</>,
                <>A <Strong>route check</Strong> fails if any API route can be reached without signing in, unless it is on an explicit public list.</>,
                <>A <Strong>security review</Strong> found 14 issues. Each is fixed and has a test that fails if the problem returns.</>,
                <>On every push to <Code>main</Code>, GitHub Actions runs linting, the tests, a database migration check, the frontend build, Docker builds and dependency security audits.</>,
              ]}
            />
            <Details summary="Test and CI specifics">
              <Bullets
                items={[
                  <>Tests are spread over 39 unit files and 18 integration files; the full run takes about 100 seconds.</>,
                  <>The migration check applies all ten migrations, removes them all, and applies them again.</>,
                  <>The security tests include 41 regression tests in <Code>test_security_regressions.py</Code>, and the route inventory also checks that placing live orders needs the live-trading permission.</>,
                  <>Other tests cover stream-owner election, candle saving, rate limiting, and a check that every scheduled job is registered.</>,
                  <>The frontend has no unit tests; it is checked by TypeScript type-checking, ESLint with zero warnings allowed, and a production build.</>,
                ]}
              />
            </Details>

            <H3 id="outcomes-lessons">Lessons learned</H3>
            <Bullets
              items={[
                <><Strong>Never trust a model’s numbers — recompute them.</Strong> The real runs above show models leaving out stop-losses and returning broken answers. The validator caught both.</>,
                <><Strong>Prove “done” by running it.</Strong> An earlier version of the project’s status file claimed it was 100% complete while the app could not even start. The current file lists only what has been verified.</>,
                <><Strong>Small infrastructure details change results.</Strong> Binance’s testnet keeps only about 28 days of price history, which quietly limited every backtest until history was read from the main exchange instead.</>,
                <><Strong>Security needs tests that keep it fixed.</Strong> Each of the 14 security fixes has a test, so a later change cannot quietly undo it.</>,
              ]}
            />
          </Section>

          {/* ── 7 Limitations ─────────────────────────────────── */}
          <Section
            id="limitations"
            num={7}
            title="Limitations"
            lead="What QuantX does not do yet, so nothing here reads as more finished than it is."
          >
            <Bullets items={LIMITATIONS} />
          </Section>

          {/* ── 8 Try it ──────────────────────────────────────── */}
          <Section id="try" num={8} title="Try it yourself" lead="See the live site, or run the full product on your own computer.">
            <H3 id="try-live">The live site</H3>
            <P>
              The public site is at{' '}
              <a href={LIVE_SITE} target="_blank" rel="noreferrer" className="text-brand-300 underline decoration-brand-500/40 underline-offset-4 hover:text-brand-200">
                quantx-dpu.pages.dev
              </a>{' '}
              and the source code is on{' '}
              <a href={REPO} target="_blank" rel="noreferrer" className="text-brand-300 underline decoration-brand-500/40 underline-offset-4 hover:text-brand-200">
                GitHub
              </a>
              .
            </P>
            <Callout title="Status on 23 November 2026" tone="warning">
              The home page loads, but the hosted server behind it is offline, so signing in on the live site will fail.
              Run QuantX locally to use it — it takes a few commands.
            </Callout>

            <H3 id="try-local">Run it locally</H3>
            <P>You need Docker with Docker Compose. Then run:</P>
            <CodeBlock label="Shell" code={LOCAL_SETUP} />
            <P>
              Open <Code>http://localhost:5173</Code>, create an account, and follow the dashboard checklist. The AI agents
              need a model; the cheapest option is a free one that runs on your computer:
            </P>
            <CodeBlock label="Optional · free local AI" code={OLLAMA_SETUP} />
            <P>
              Or set <Code>ANTHROPIC_API_KEY</Code> to use Claude. For live prices instead of 15-second refreshes, set{' '}
              <Code>MARKET_STREAM_ENABLED=true</Code>.
            </P>

            <H3 id="try-api">Call the API</H3>
            <P>
              The API is also available on <Code>localhost:8000</Code>. This signs in, opens a paper account and asks the
              four agents for a decision:
            </P>
            <CodeBlock label="Shell" code={API_WALKTHROUGH} />
            <P>
              Interactive documentation for all 67 operations is at <Code>http://localhost:8000/docs</Code> (outside
              production mode).
            </P>
          </Section>

          <footer className="mt-16 flex flex-col gap-4 border-t border-white/[0.06] pt-8 text-xs text-zinc-500 sm:flex-row sm:items-center sm:justify-between">
            <p>Checked against the code at commit 5f1fb3a, 23 November 2026. Research software · not financial advice.</p>
            <div className="flex gap-5">
              <a href="/" className="hover:text-white cursor-pointer">Home</a>
              <a href="#problem" className="hover:text-white cursor-pointer">Back to top</a>
              <a href={REPO} target="_blank" rel="noreferrer" className="hover:text-white cursor-pointer">Source</a>
            </div>
          </footer>
        </main>
      </div>
    </div>
  );
}
