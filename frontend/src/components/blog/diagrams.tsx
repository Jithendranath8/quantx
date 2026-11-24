/**
 * Diagrams for the /blog write-up. Every box and edge here mirrors something
 * in the code (module, table, route, schedule); when the code changes, change
 * these too. Drawn as inline SVG against the app's own colour tokens.
 */
import { useId } from 'react';
import type { ReactNode } from 'react';

const halo = { paintOrder: 'stroke', stroke: '#07080a', strokeWidth: 5, strokeLinejoin: 'round' } as const;

function Arrowheads({ id }: { id: string }) {
  return (
    <defs>
      <marker id={`${id}-a`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" className="fill-zinc-400" />
      </marker>
      <marker id={`${id}-b`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" className="fill-brand-400" />
      </marker>
    </defs>
  );
}

function Box({
  x,
  y,
  w,
  h,
  title,
  lines = [],
  tone = 'default',
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  title: string;
  lines?: string[];
  tone?: 'default' | 'external' | 'brand' | 'inner';
}) {
  const rectClass = {
    default: 'fill-ink-850 stroke-white/15',
    external: 'fill-ink-950 stroke-white/25',
    brand: 'fill-brand-500/[0.06] stroke-brand-400/60',
    inner: 'fill-ink-900 stroke-white/10',
  }[tone];
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={12}
        className={rectClass}
        strokeDasharray={tone === 'external' ? '5 4' : undefined}
      />
      <text x={x + w / 2} y={y + 24} textAnchor="middle" className="fill-white text-[13.5px] font-medium">
        {title}
      </text>
      {lines.map((line, i) => (
        <text key={line} x={x + w / 2} y={y + 43 + i * 16} textAnchor="middle" className="fill-zinc-400 text-[11.5px]">
          {line}
        </text>
      ))}
    </g>
  );
}

function Edge({
  d,
  id,
  brand = false,
  dashed = false,
  label,
  lx,
  ly,
  anchor = 'middle',
}: {
  d: string;
  id: string;
  brand?: boolean;
  dashed?: boolean;
  label?: string;
  lx?: number;
  ly?: number;
  anchor?: 'start' | 'middle' | 'end';
}) {
  return (
    <g>
      <path
        d={d}
        fill="none"
        className={brand ? 'stroke-brand-400' : 'stroke-zinc-500'}
        strokeWidth={1.5}
        strokeDasharray={dashed ? '5 4' : undefined}
        markerEnd={`url(#${id}-${brand ? 'b' : 'a'})`}
      />
      {label && lx !== undefined && ly !== undefined && (
        <text x={lx} y={ly} textAnchor={anchor} className="fill-zinc-400 font-mono text-[10.5px]" style={halo}>
          {label}
        </text>
      )}
    </g>
  );
}

/** Whole-system view: browser, proxy, API, datastores, workers and external services. */
export function ArchitectureDiagram() {
  const id = useId().replace(/:/g, '');
  return (
    <svg
      viewBox="0 0 960 590"
      width="100%"
      role="img"
      aria-label="QuantX system architecture: browser to nginx to FastAPI, which talks to PostgreSQL, two Redis instances, Celery workers, Binance, an LLM provider, and shares its tool layer with an MCP server."
      className="block font-sans"
      style={{ minWidth: 760 }}
    >
      <Arrowheads id={id} />

      {/* Client side */}
      <Box x={16} y={236} w={170} h={92} title="Browser" lines={['React 18 SPA', 'Vite · Tailwind · TS']} />
      <Box x={226} y={236} w={150} h={92} title="nginx" lines={['serves the SPA', 'proxies /api and /ws']} />

      {/* External services */}
      <Box x={420} y={16} w={260} h={70} title="Binance API" lines={['REST + WebSocket · SPOT']} tone="external" />
      <Box x={420} y={500} w={260} h={74} title="LLM provider" lines={['Anthropic Claude, or any', 'OpenAI-compatible (e.g. Ollama)']} tone="external" />

      {/* Backend */}
      <rect x={420} y={118} width={260} height={334} rx={16} className="fill-brand-500/[0.04] stroke-brand-400/60" />
      <text x={550} y={144} textAnchor="middle" className="fill-white text-[14px] font-semibold">
        FastAPI backend
      </text>
      <Box x={438} y={160} w={224} h={56} title="REST API · /api/v1" lines={['67 operations · JWT · limits']} tone="inner" />
      <Box x={438} y={224} w={224} h={56} title="WebSocket gateway · /ws" lines={['market ticks to the browser']} tone="inner" />
      <Box x={438} y={288} w={224} h={56} title="Agents · tools · LangGraph" lines={['provider-agnostic LLM runtime']} tone="inner" />
      <Box x={438} y={352} w={224} h={84} title="Services → engines" lines={['paper · live · risk · backtest', 'research · indicators', 'market making']} tone="inner" />

      {/* Datastores and workers */}
      <Box x={730} y={30} w={214} h={78} title="PostgreSQL 16" lines={['users · candles · orders', 'AI logs · experiments']} />
      <Box x={730} y={140} w={214} h={78} title="Redis · cache" lines={['allkeys-lru', 'pub/sub · rate limits · locks']} />
      <Box x={730} y={250} w={214} h={78} title="Redis · broker" lines={['noeviction', 'Celery job queue']} />
      <Box x={730} y={360} w={214} h={92} title="Celery worker + beat" lines={['paper fills · market sync', 'AI settlement · reconcile', 'retention prune']} />

      {/* MCP */}
      <Box x={16} y={470} w={170} h={76} title="MCP client" lines={['e.g. Claude Code']} tone="external" />
      <Box x={226} y={470} w={150} h={76} title="MCP server" lines={['stdio · same tools']} />

      {/* Edges */}
      <Edge id={id} d="M186 282 H222" brand label="HTTPS" lx={204} ly={270} />
      <Edge id={id} d="M376 282 H434" brand label="/api /ws" lx={404} ly={270} />
      <Edge id={id} d="M550 118 V90" label="prices · klines · orders" lx={540} ly={108} anchor="end" />
      <Edge id={id} d="M550 452 V496" label="chat + tool calls" lx={560} ly={480} anchor="start" />
      <Edge id={id} d="M680 136 H704 V69 H726" />
      <Edge id={id} d="M680 179 H726" />
      <Edge id={id} d="M680 289 H726" label="enqueue" lx={703} ly={281} />
      <Edge id={id} d="M837 328 V356" />
      <Edge id={id} d="M944 406 H954 V69 H948" label="writes" lx={950} ly={240} anchor="end" />
      <Edge id={id} d="M186 508 H222" label="stdio" lx={204} ly={498} />
      <Edge id={id} d="M376 508 H400 V316 H434" dashed label="imports the tool layer" lx={392} ly={460} anchor="end" />
    </svg>
  );
}

/** The LangGraph state machine behind POST /api/v1/agent/orchestrate. */
export function AgentGraphDiagram() {
  const id = useId().replace(/:/g, '');
  const top: { key: string; x: number; label: string; tools?: string[] }[] = [
    { key: 'init', x: 76, label: 'init', tools: ['get_price'] },
    { key: 'market', x: 222, label: 'market', tools: ['get_price', 'get_klines', 'get_indicators'] },
    { key: 'technical', x: 368, label: 'technical', tools: ['get_indicators', 'get_klines'] },
    { key: 'quant', x: 514, label: 'quant', tools: ['list_strategies', 'run_backtest', 'predict_direction'] },
    { key: 'risk', x: 660, label: 'risk', tools: ['validate_trade', 'get_risk_state'] },
  ];
  const W = 124;
  return (
    <svg
      viewBox="0 0 960 330"
      width="100%"
      role="img"
      aria-label="Orchestration graph: start, init, market, technical, quant and risk specialists, synthesis, deterministic gates, then either a paper execution step or the end."
      className="block font-sans"
      style={{ minWidth: 760 }}
    >
      <Arrowheads id={id} />

      {/* START */}
      <circle cx={34} cy={52} r={14} className="fill-zinc-200" />
      <text x={34} y={86} textAnchor="middle" className="fill-zinc-500 font-mono text-[10px]">START</text>
      <Edge id={id} d={`M48 52 H${top[0].x - 4}`} />

      {top.map((node, i) => (
        <g key={node.key}>
          <rect
            x={node.x}
            y={30}
            width={W}
            height={44}
            rx={10}
            className={i === 0 ? 'fill-ink-850 stroke-white/20' : 'fill-brand-500/[0.07] stroke-brand-400/60'}
          />
          <text x={node.x + W / 2} y={57} textAnchor="middle" className="fill-white text-[13.5px] font-medium">
            {node.label}
          </text>
          {node.tools?.map((t, j) => (
            <text key={t} x={node.x + W / 2} y={96 + j * 15} textAnchor="middle" className="fill-zinc-400 font-mono text-[10.5px]">
              {t}
            </text>
          ))}
          {i < top.length - 1 && <Edge id={id} d={`M${node.x + W} 52 H${top[i + 1].x - 4}`} />}
        </g>
      ))}

      <text x={490} y={160} textAnchor="middle" className="fill-zinc-500 text-[11px]">
        Each specialist = the same bounded tool loop (max 8 rounds), its own prompt, only the tools listed under it
      </text>

      {/* Right from risk, then down to synthesis (clear of the tool names) */}
      <Edge id={id} d={`M${660 + W} 52 H874 V196`} />

      {/* Bottom row, right to left */}
      <rect x={812} y={200} width={124} height={44} rx={10} className="fill-ink-850 stroke-white/20" />
      <text x={874} y={221} textAnchor="middle" className="fill-white text-[13.5px] font-medium">synthesis</text>
      <text x={874} y={236} textAnchor="middle" className="fill-zinc-500 font-mono text-[10px]">no tools · JSON</text>

      <Edge id={id} d="M812 222 H756" />
      <rect x={600} y={196} width={152} height={52} rx={10} className="fill-ink-850 stroke-emerald-400/50" />
      <text x={676} y={217} textAnchor="middle" className="fill-white text-[13px] font-medium">deterministic gates</text>
      <text x={676} y={234} textAnchor="middle" className="fill-zinc-500 font-mono text-[10px]">any failure → WAIT</text>

      <Edge id={id} d="M600 222 H546" />
      <polygon points="500,192 542,222 500,252 458,222" className="fill-ink-900 stroke-white/25" />
      <text x={500} y={226} textAnchor="middle" className="fill-zinc-300 font-mono text-[11px]">route</text>

      <Edge id={id} d="M458 222 H292" brand />
      <text x={374} y={198} textAnchor="middle" className="fill-brand-300 font-mono text-[10.5px]" style={halo}>execute=true</text>
      <text x={374} y={212} textAnchor="middle" className="fill-brand-300 font-mono text-[10.5px]" style={halo}>BUY/SELL · not halted</text>
      <rect x={150} y={200} width={138} height={44} rx={10} className="fill-brand-500/[0.07] stroke-brand-400/60" strokeDasharray="5 4" />
      <text x={219} y={221} textAnchor="middle" className="fill-white text-[13px] font-medium">execution</text>
      <text x={219} y={236} textAnchor="middle" className="fill-zinc-500 font-mono text-[10px]">submit_paper_order</text>

      <Edge id={id} d="M150 222 H76" brand />
      <circle cx={58} cy={222} r={14} className="fill-none stroke-zinc-200" strokeWidth={2} />
      <circle cx={58} cy={222} r={8} className="fill-zinc-200" />
      <text x={38} y={226} textAnchor="end" className="fill-zinc-500 font-mono text-[10px]">END</text>

      <Edge id={id} d="M500 252 V292 H58 V240" label="otherwise (the default)" lx={280} ly={284} />
    </svg>
  );
}

interface Col {
  name: string;
  tag?: string;
}

function Table({ x, y, name, cols, w = 208 }: { x: number; y: number; name: string; cols: Col[]; w?: number }) {
  const h = 32 + cols.length * 20 + 6;
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={10} className="fill-ink-850 stroke-white/15" />
      <path d={`M${x} ${y + 30} H${x + w}`} className="stroke-white/10" />
      <text x={x + 12} y={y + 20} className="fill-white font-mono text-[12.5px] font-medium">
        {name}
      </text>
      {cols.map((c, i) => (
        <g key={c.name}>
          <text x={x + 12} y={y + 48 + i * 20} className="fill-zinc-300 font-mono text-[11px]">
            {c.name}
          </text>
          {c.tag && (
            <text x={x + w - 10} y={y + 48 + i * 20} textAnchor="end" className="fill-brand-300/90 font-mono text-[10px]">
              {c.tag}
            </text>
          )}
        </g>
      ))}
    </g>
  );
}

/** Core tables and how they relate. Columns shown are a subset of the real ones. */
export function DataModelDiagram() {
  const id = useId().replace(/:/g, '');
  const A = 16;
  const B = 256;
  const C = 496;
  const D = 736;
  const owner = '→ users';
  return (
    <svg
      viewBox="0 0 960 690"
      width="100%"
      role="img"
      aria-label="Entity relationship diagram of the core QuantX tables grouped as identity, paper trading, live trading and risk, and market data, AI and research."
      className="block font-sans"
      style={{ minWidth: 760 }}
    >
      <Arrowheads id={id} />
      {[
        [A, 'IDENTITY'],
        [B, 'PAPER TRADING'],
        [C, 'LIVE TRADING · RISK · AUDIT'],
        [D, 'MARKET DATA · AI · RESEARCH'],
      ].map(([x, label]) => (
        <text key={label} x={Number(x) + 2} y={20} className="fill-brand-400 font-mono text-[10.5px] tracking-[0.14em]">
          {label}
        </text>
      ))}

      <Table x={A} y={34} name="users" cols={[{ name: 'id', tag: 'PK' }, { name: 'email', tag: 'UNIQUE' }, { name: 'oauth_provider' }, { name: 'oauth_subject' }, { name: 'can_trade_live' }]} />
      <Table x={A} y={212} name="refresh_tokens" cols={[{ name: 'user_id', tag: 'FK' }, { name: 'token_hash' }, { name: 'family_id' }, { name: 'expires_at' }]} />
      <Table x={A} y={370} name="audit_logs" cols={[{ name: 'user_id', tag: owner }, { name: 'action' }, { name: 'resource_type' }]} />

      <Table x={B} y={34} name="paper_accounts" cols={[{ name: 'id', tag: 'PK' }, { name: 'user_id', tag: owner }, { name: 'current_balance' }, { name: 'realized_pnl' }]} />
      <Table x={B} y={192} name="paper_orders" cols={[{ name: 'account_id' }, { name: 'symbol · side' }, { name: 'order_type' }, { name: 'status', tag: 'PENDING…' }, { name: 'filled_price' }, { name: 'realized_pnl' }]} />
      <Table x={B} y={390} name="paper_positions" cols={[{ name: 'account_id' }, { name: 'symbol' }, { name: 'quantity' }, { name: 'entry_price' }, { name: 'status', tag: '1 OPEN/sym' }]} />

      <Table x={C} y={34} name="live_orders" cols={[{ name: 'user_id', tag: owner }, { name: 'client_order_id', tag: 'UNIQUE' }, { name: 'exchange_order_id' }, { name: 'status' }, { name: 'is_testnet' }]} />
      <Table x={C} y={212} name="risk_state" cols={[{ name: 'user_id', tag: 'UNIQUE' }, { name: 'circuit_breaker_active' }, { name: 'daily_loss_usd' }]} />
      <Table x={C} y={350} name="event_ledger" cols={[{ name: 'user_id', tag: owner }, { name: 'source' }, { name: 'event_type' }, { name: 'payload', tag: 'JSONB' }]} />

      <Table x={D} y={34} name="candles" cols={[{ name: 'symbol', tag: 'UNIQUE' }, { name: 'timeframe', tag: '  (together)' }, { name: 'timestamp' }, { name: 'open · high · low · close' }]} />
      <Table x={D} y={192} name="ai_decision_logs" cols={[{ name: 'user_id', tag: owner }, { name: 'action · confidence' }, { name: 'was_validated' }, { name: 'latency_ms · tokens' }, { name: 'outcome_source' }]} />
      <Table x={D} y={370} name="experiment_records" cols={[{ name: 'user_id', tag: owner }, { name: 'strategy_name' }, { name: 'dataset_version' }, { name: 'metrics', tag: 'JSONB' }, { name: 'git_commit' }]} />
      <Table x={D} y={562} name="dataset_fingerprints" cols={[{ name: 'dataset_hash', tag: 'UNIQUE' }, { name: 'row_count' }, { name: 'start · end' }]} />

      {/* Relationships */}
      <Edge id={id} d={`M${A + 104} 212 V178`} brand label="FK · cascade" lx={A + 112} ly={200} anchor="start" />
      <Edge id={id} d={`M${B + 104} 192 V158`} dashed label="account_id" lx={B + 112} ly={180} anchor="start" />
      <Edge id={id} d={`M${B + 208} 420 H${B + 224} V96 H${B + 212}`} dashed />
      <Edge id={id} d={`M${D + 104} 492 V558`} dashed label="dataset_version = hash" lx={D + 96} ly={530} anchor="end" />

      {/* Legend */}
      <g>
        <path d="M18 620 H58" className="stroke-brand-400" strokeWidth={1.5} />
        <text x={66} y={624} className="fill-zinc-400 text-[11.5px]">foreign key declared in the database</text>
        <path d="M18 644 H58" className="stroke-zinc-500" strokeWidth={1.5} strokeDasharray="5 4" />
        <text x={66} y={648} className="fill-zinc-400 text-[11.5px]">reference checked in service code (no FK constraint)</text>
        <text x={18} y={672} className="fill-brand-300/90 font-mono text-[10.5px]">→ users</text>
        <text x={66} y={672} className="fill-zinc-400 text-[11.5px]">column holds the owning user&apos;s id (a plain UUID, no FK constraint)</text>
      </g>
    </svg>
  );
}

/** One step in a horizontal (wrapping on mobile) flow strip. */
function FlowStep({ title, body, accent = false }: { title: string; body: ReactNode; accent?: boolean }) {
  return (
    <li
      className={`relative flex-1 min-w-[150px] rounded-2xl border px-4 py-3 ${
        accent ? 'border-brand-500/30 bg-brand-500/[0.06]' : 'border-white/[0.08] bg-ink-900/70'
      }`}
    >
      <p className="text-sm font-medium text-white">{title}</p>
      <p className="mt-1 text-xs leading-relaxed text-zinc-400">{body}</p>
    </li>
  );
}

/** Live market data, from Binance to a browser tab, as implemented in app/websockets. */
export function MarketDataPath() {
  return (
    <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5" aria-label="Live market data path">
      <FlowStep title="Binance stream" body="Combined kline + partial-depth WebSocket for every configured symbol." />
      <FlowStep
        title="One owner worker"
        body={<>A Redis key with a 30 s TTL elects one process; it renews every 10 s with compare-and-swap.</>}
        accent
      />
      <FlowStep title="Normalise + validate" body="Each message is normalised; closed bars are upserted into candles." />
      <FlowStep title="Redis pub/sub" body="Ticks are published per symbol, so any API worker can serve any socket." />
      <FlowStep title="Gateway → browser" body="/ws/market/{symbol} checks the access token, then fans ticks out." accent />
    </ol>
  );
}

/**
 * The whole idea of QuantX in four boxes: the path every AI suggestion takes.
 * Mirrors graph.py (synthesis → gates → execution) and paper_trading_service.py.
 */
export function DecisionPipeline() {
  const steps: { n: string; title: string; body: string; tone: 'ai' | 'check' | 'act' }[] = [
    { n: '1', title: 'AI agents suggest', body: 'BUY, SELL or WAIT, with an entry price, a stop-loss and a target.', tone: 'ai' },
    { n: '2', title: 'Validator checks the math', body: 'Plain code re-checks every number the AI gave.', tone: 'check' },
    { n: '3', title: 'Risk engine checks limits', body: 'Before any order fills: size, exposure and daily-loss limits the AI cannot change.', tone: 'check' },
    { n: '4', title: 'Paper order, only if allowed', body: 'Filled with play money at real prices. No path leads to real money.', tone: 'act' },
  ];
  const tone = {
    ai: 'border-brand-500/30 bg-brand-500/[0.06]',
    check: 'border-emerald-500/25 bg-emerald-500/[0.05]',
    act: 'border-white/[0.1] bg-ink-900/70',
  };
  return (
    <div className="p-4 sm:p-6">
      <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="The path every AI suggestion takes">
        {steps.map((s, i) => (
          <li key={s.n} className={`relative rounded-2xl border p-4 ${tone[s.tone]}`}>
            <span className="font-mono text-xs text-brand-400">Step {s.n}</span>
            <p className="mt-1 text-[15px] font-medium text-white">{s.title}</p>
            <p className="mt-1.5 text-[13px] leading-relaxed text-zinc-400">{s.body}</p>
            {i < steps.length - 1 && (
              <span
                aria-hidden="true"
                className="absolute -right-2.5 top-1/2 hidden h-5 w-5 -translate-y-1/2 place-items-center rounded-full bg-ink-950 text-xs text-zinc-500 ring-1 ring-white/10 lg:grid"
              >
                →
              </span>
            )}
          </li>
        ))}
      </ol>
      <p className="mt-4 rounded-xl border border-yellow-500/20 bg-yellow-500/[0.05] px-4 py-2.5 text-[13px] text-yellow-200/90">
        If step 2 fails, the answer becomes <strong className="font-semibold">WAIT</strong> (do nothing), with the reason
        attached. If step 3 fails, the order is refused. Either way, nothing is traded.
      </p>
    </div>
  );
}

/** The backend's layering, with the folder each layer lives in. */
export function BackendLayers() {
  const layers: { name: string; dir: string; body: string }[] = [
    { name: 'Routes', dir: 'app/api/v1/endpoints', body: 'HTTP shape only: auth, rate limits, input bounds, response models.' },
    { name: 'Agents', dir: 'app/agents', body: 'LLM runtime, tools and the LangGraph graph. Reaches services only through tools.' },
    { name: 'Services', dir: 'app/services', body: 'Business rules and transactions: paper and live trading, risk state, backtests, AI logs.' },
    { name: 'Engines', dir: 'app/engines', body: 'Calculations: indicators, risk manager, backtester, research, market making. Nearly all are pure; the multi-timeframe indicator engine reads stored candles itself.' },
    { name: 'Connectors & models', dir: 'app/connectors · app/models', body: 'Signed Binance client and SQLAlchemy tables. Migrations 001–010 live in alembic/versions.' },
  ];
  return (
    <ol className="space-y-2">
      {layers.map((l) => (
        <li
          key={l.name}
          className="grid gap-1 rounded-2xl border border-white/[0.07] bg-ink-900/60 px-4 py-3 sm:grid-cols-[150px_220px_minmax(0,1fr)] sm:items-center sm:gap-4"
        >
          <span className="text-sm font-medium text-white">{l.name}</span>
          <code className="font-mono text-xs text-brand-300/90 break-words">{l.dir}</code>
          <span className="text-sm text-zinc-400">{l.body}</span>
        </li>
      ))}
    </ol>
  );
}
