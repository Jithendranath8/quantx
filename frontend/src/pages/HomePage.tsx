import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { AnimatePresence, motion, useScroll, useMotionValueEvent } from 'motion/react';
import {
  Activity, ArrowRight, ArrowUpRight, Bot, Brain, Calculator, Database, FileCheck2, FlaskConical,
  Gauge, KeyRound, LineChart, Lock, Menu, ShieldCheck, Sparkles, Terminal, Wallet, X,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';

import DecisionFlow from '../components/brand/DecisionFlow';
import { Logo } from '../components/brand/Logo';
import SplineScene from '../components/fx/SplineScene';
import {
  GridBackdrop, Marquee, MovingBorderButton, Reveal, RevealWords, Spotlight, SpotlightCard,
} from '../components/fx/effects';
import { useAuth } from '../contexts/useAuth';
import { WORKSPACES, appPath } from '../lib/navigation';

const SECTIONS = [
  { id: 'how-it-works', label: 'How it works' },
  { id: 'platform', label: 'Platform' },
  { id: 'safety', label: 'Safety' },
  { id: 'start', label: 'First session' },
  { id: 'faq', label: 'FAQ' },
];

/** Floating pill navigation that tightens once the page scrolls. */
function SiteNav() {
  const { isAuthenticated } = useAuth();
  const { scrollY } = useScroll();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  useMotionValueEvent(scrollY, 'change', (y) => setScrolled(y > 24));

  return (
    <header className="fixed inset-x-0 top-0 z-50 px-4 pt-4">
      <motion.nav
        aria-label="Primary"
        animate={{ maxWidth: scrolled ? 980 : 1200 }}
        transition={{ type: 'spring', stiffness: 260, damping: 32 }}
        className={`mx-auto flex h-14 items-center gap-6 rounded-full px-3 pl-5 transition-colors duration-300 ${
          scrolled ? 'border border-white/[0.08] bg-ink-900/80 backdrop-blur-xl shadow-2xl' : 'border border-transparent'
        }`}
      >
        <Logo />
        <ul className="hidden md:flex items-center gap-1 text-sm">
          {SECTIONS.map((s) => (
            <li key={s.id}>
              <a href={`#${s.id}`} className="rounded-full px-3 py-1.5 text-zinc-400 hover:text-white transition-colors cursor-pointer">
                {s.label}
              </a>
            </li>
          ))}
        </ul>
        <div className="ml-auto flex items-center gap-2">
          {!isAuthenticated && (
            <Link to="/login" className="hidden sm:inline-flex h-9 items-center rounded-full px-4 text-sm text-zinc-300 hover:text-white cursor-pointer">
              Sign in
            </Link>
          )}
          <Link
            to={isAuthenticated ? appPath('') : '/login?mode=register'}
            className="inline-flex h-9 items-center gap-1.5 rounded-full bg-white px-4 text-sm font-medium text-ink-950 hover:bg-zinc-200 transition cursor-pointer"
          >
            {isAuthenticated ? 'Open terminal' : 'Get started'}
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
          <button
            type="button"
            className="md:hidden p-2 text-zinc-300 cursor-pointer"
            aria-label={open ? 'Close menu' : 'Open menu'}
            onClick={() => setOpen((o) => !o)}
          >
            {open ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </motion.nav>
      <AnimatePresence>
        {open && (
          <motion.ul
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="md:hidden mx-auto mt-2 max-w-[1200px] rounded-3xl border border-white/10 bg-ink-900/95 p-2 backdrop-blur-xl"
          >
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <a href={`#${s.id}`} onClick={() => setOpen(false)} className="block rounded-2xl px-4 py-3 text-sm text-zinc-300 hover:bg-white/5">
                  {s.label}
                </a>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </header>
  );
}

function Hero() {
  const { isAuthenticated } = useAuth();
  return (
    <section className="relative overflow-hidden pt-36 pb-20 lg:pt-40 lg:pb-28">
      <Spotlight className="-top-40 left-0 md:-top-20 md:left-40" />
      <GridBackdrop />
      <div className="relative mx-auto grid max-w-[1200px] items-center gap-10 px-6 lg:grid-cols-[1.05fr_1fr]">
        <div>
          <Reveal>
            <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-zinc-300">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-400 opacity-70" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-brand-400" />
              </span>
              Agentic research terminal for crypto markets
            </span>
          </Reveal>
          <h1 className="mt-6 font-display text-[clamp(2.8rem,6.4vw,5.4rem)] leading-[0.98] tracking-tight text-white">
            <RevealWords text="Let the agents argue." />
            <br />
            <em className="text-brand-400">
              <RevealWords text="Let the math decide." />
            </em>
          </h1>
          <Reveal delay={0.35}>
            <p className="mt-6 max-w-xl text-base leading-relaxed text-zinc-400 sm:text-lg">
              QuantX watches live Binance markets, lets a team of AI specialists propose trades, then re-checks every
              proposal with plain arithmetic and hard risk limits before anything touches an account — a paper account,
              by default.
            </p>
          </Reveal>
          <Reveal delay={0.5}>
            <div className="mt-9 flex flex-wrap items-center gap-4">
              <Link to={isAuthenticated ? appPath('') : '/login?mode=register'} className="group cursor-pointer">
                <MovingBorderButton>
                  {isAuthenticated ? 'Open the terminal' : 'Start researching — free'}
                  <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
                </MovingBorderButton>
              </Link>
              <a href="#how-it-works" className="inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white transition cursor-pointer">
                See how a decision is made <ArrowUpRight className="w-4 h-4" />
              </a>
            </div>
          </Reveal>
          <Reveal delay={0.65}>
            <dl className="mt-12 grid max-w-lg grid-cols-3 gap-6 border-t border-white/[0.07] pt-6">
              {[
                ['Paper', 'trading by default'],
                ['2 flags', 'required for a real order'],
                ['100%', 'of actions audited'],
              ].map(([k, v]) => (
                <div key={k}>
                  <dt className="font-mono text-lg text-white">{k}</dt>
                  <dd className="mt-1 text-xs text-zinc-500">{v}</dd>
                </div>
              ))}
            </dl>
          </Reveal>
        </div>

        <div className="relative hidden h-[560px] lg:block">
          <div className="absolute inset-0 rounded-[2rem] bg-[radial-gradient(circle_at_50%_45%,rgba(255,122,26,0.18),transparent_60%)]" />
          <SplineScene className="h-full w-full" />
          <p className="pointer-events-none absolute bottom-3 right-4 font-mono text-[10px] text-zinc-600">move your cursor</p>
        </div>
      </div>
    </section>
  );
}

const CAPABILITIES = [
  'Live Binance market data', 'Order-book depth', 'Multi-timeframe indicators', 'Strategy engine',
  'LangGraph multi-agent analysis', 'Deterministic decision validator', 'Persisted risk engine',
  'Paper trading with slippage & fees', 'Event-driven backtests', 'Walk-forward analysis',
  'Monte Carlo', 'Avellaneda–Stoikov market making', 'LSTM direction model', 'MCP server',
];

function CapabilityStrip() {
  return (
    <section aria-label="Capabilities" className="border-y border-white/[0.06] bg-ink-900/40 py-5">
      <Marquee
        items={CAPABILITIES.map((c) => (
          <span key={c} className="inline-flex items-center gap-2 rounded-full border border-white/[0.07] bg-white/[0.02] px-4 py-1.5 text-sm text-zinc-400">
            <Sparkles className="w-3.5 h-3.5 text-brand-400/80" /> {c}
          </span>
        ))}
      />
    </section>
  );
}

function SectionHeading({ eyebrow, title, body }: { eyebrow: string; title: ReactNode; body?: string }) {
  return (
    <Reveal className="max-w-2xl">
      <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-brand-400">{eyebrow}</p>
      <h2 className="mt-4 font-display text-[clamp(2.2rem,4.4vw,3.6rem)] leading-[1.02] text-white">{title}</h2>
      {body && <p className="mt-5 text-base leading-relaxed text-zinc-400">{body}</p>}
    </Reveal>
  );
}

const PIPELINE: { icon: LucideIcon; title: string; page: string; body: string; points: string[] }[] = [
  {
    icon: Database,
    title: 'Observe',
    page: 'Markets → Market Data',
    body: 'Live prices, order-book depth, funding and open interest stream in from Binance and are stored as candles.',
    points: ['WebSocket ticker and depth', 'Historical candles for every timeframe', 'Microstructure: spread, imbalance, VWAP'],
  },
  {
    icon: LineChart,
    title: 'Analyse',
    page: 'Markets → Indicators',
    body: 'Indicators are computed across timeframes and an optional ML model estimates price direction.',
    points: ['RSI, MACD, Bollinger, ATR, moving averages', 'Trend agreement across 15m, 1h and 4h', 'PyTorch LSTM direction model'],
  },
  {
    icon: Bot,
    title: 'Propose',
    page: 'Research → AI Agent',
    body: 'Specialist agents — market, technical, quant and risk — reason over that data and a supervisor synthesises one decision.',
    points: ['BUY, SELL or WAIT with entry, stop and target', 'Confidence and written reasoning', 'Works with Claude or any OpenAI-compatible model'],
  },
  {
    icon: Calculator,
    title: 'Gate',
    page: 'Trading → Risk Engine',
    body: 'A deterministic validator recomputes the arithmetic, then every buy — paper or live — must pass risk limits no model can override.',
    points: ['Stops on the correct side, sane reward-to-risk', 'Position, exposure and daily-loss caps', 'Circuit breaker that halts everything'],
  },
  {
    icon: Wallet,
    title: 'Act',
    page: 'Trading → Paper Trading',
    body: 'Surviving decisions become paper orders filled against live prices with slippage and fees. Live trading needs two separate flags.',
    points: ['Market, limit, stop-loss and take-profit orders', 'Positions and P&L update in real time', 'Mainnet requires BINANCE_TESTNET=false and ALLOW_MAINNET_TRADING=true'],
  },
  {
    icon: FileCheck2,
    title: 'Audit',
    page: 'Insights → Event Ledger',
    body: 'Every proposal, rejection, order and risk event is recorded, so you can see exactly why something happened.',
    points: ['Immutable event ledger', 'AI decision log with latency, tokens and cost', 'Outcome tracking per decision'],
  },
];

/** Interactive pipeline: pick a stage (or let it auto-advance) to see what happens there. */
function HowItWorks() {
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const stage = PIPELINE[active];

  useEffect(() => {
    if (paused || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const id = window.setTimeout(() => setActive((a) => (a + 1) % PIPELINE.length), 5200);
    return () => window.clearTimeout(id);
  }, [active, paused]);

  return (
    <section id="how-it-works" className="scroll-mt-24 py-28">
      <div className="mx-auto max-w-[1200px] px-6">
        <SectionHeading
          eyebrow="How it works"
          title={<>Six stages, from tick <em className="text-zinc-500">to audit trail.</em></>}
          body="Every idea in QuantX travels the same path. Knowing it is the fastest way to understand every screen in the app."
        />

        <div
          className="mt-14 grid gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]"
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
        >
          <ol className="space-y-2" role="tablist" aria-label="Pipeline stages">
            {PIPELINE.map((p, i) => {
              const selected = i === active;
              return (
                <li key={p.title}>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={selected}
                    onClick={() => setActive(i)}
                    onFocus={() => setPaused(true)}
                    className={`relative w-full overflow-hidden rounded-2xl border px-5 py-4 text-left transition-colors cursor-pointer ${
                      selected ? 'border-white/10 bg-ink-850' : 'border-transparent hover:bg-white/[0.02]'
                    }`}
                  >
                    <div className="flex items-center gap-4">
                      <span className={`font-mono text-xs ${selected ? 'text-brand-400' : 'text-zinc-600'}`}>0{i + 1}</span>
                      <p.icon className={`w-4 h-4 ${selected ? 'text-white' : 'text-zinc-500'}`} />
                      <span className={`text-base ${selected ? 'text-white' : 'text-zinc-400'}`}>{p.title}</span>
                      <span className="ml-auto hidden sm:block text-xs text-zinc-600">{p.page}</span>
                    </div>
                    {selected && !paused && (
                      <motion.span
                        key={`progress-${active}`}
                        className="absolute bottom-0 left-0 h-px bg-brand-500"
                        initial={{ width: '0%' }}
                        animate={{ width: '100%' }}
                        transition={{ duration: 5.2, ease: 'linear' }}
                      />
                    )}
                  </button>
                </li>
              );
            })}
          </ol>

          <SpotlightCard className="min-h-[360px] p-8 sm:p-10">
            <AnimatePresence mode="wait">
              <motion.div
                key={stage.title}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.3 }}
              >
                <div className="flex items-center gap-3">
                  <span className="grid h-12 w-12 place-items-center rounded-2xl bg-brand-500/10 text-brand-300 ring-1 ring-inset ring-brand-500/25">
                    <stage.icon className="w-5 h-5" />
                  </span>
                  <div>
                    <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-zinc-500">Stage 0{active + 1}</p>
                    <h3 className="font-display text-3xl text-white">{stage.title}</h3>
                  </div>
                </div>
                <p className="mt-6 text-lg leading-relaxed text-zinc-300">{stage.body}</p>
                <ul className="mt-6 space-y-3">
                  {stage.points.map((pt) => (
                    <li key={pt} className="flex gap-3 text-sm text-zinc-400">
                      <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-brand-400" />
                      <span className="break-words">{pt}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-8 inline-flex items-center gap-2 rounded-full border border-white/[0.07] px-3 py-1 font-mono text-[11px] text-zinc-500">
                  In the app: {stage.page}
                </p>
              </motion.div>
            </AnimatePresence>
          </SpotlightCard>
        </div>
      </div>
    </section>
  );
}

const WORKSPACE_ICONS: Record<string, LucideIcon> = {
  overview: Gauge,
  markets: Activity,
  trading: Wallet,
  research: FlaskConical,
  insights: Brain,
};

/** The app's five workspaces, so nobody walks into the dashboard blind. */
function PlatformMap() {
  const [first, ...rest] = WORKSPACES;
  return (
    <section id="platform" className="scroll-mt-24 border-t border-white/[0.06] py-28">
      <div className="mx-auto max-w-[1200px] px-6">
        <SectionHeading
          eyebrow="Where everything lives"
          title={<>Five workspaces. <em className="text-zinc-500">One question each.</em></>}
          body="Inside the app, pages are grouped by the question they answer. You only ever see the handful that matter to what you are doing right now."
        />
        <div className="mt-14 grid gap-4 md:grid-cols-6">
          {[first, ...rest].map((w, i) => {
            const Icon = WORKSPACE_ICONS[w.id];
            // Bento rhythm: two wide tiles over three, then the rest.
            const span = i < 2 ? 'md:col-span-3' : 'md:col-span-2';
            return (
              <Reveal key={w.id} delay={i * 0.05} className={span}>
                <SpotlightCard className="h-full p-7">
                  <div className="flex items-start justify-between">
                    <span className="grid h-10 w-10 place-items-center rounded-xl bg-white/[0.04] text-zinc-300 ring-1 ring-inset ring-white/[0.08]">
                      <Icon className="w-4 h-4" />
                    </span>
                    <span className="font-mono text-[11px] text-zinc-600">{w.pages.length} {w.pages.length === 1 ? 'page' : 'pages'}</span>
                  </div>
                  <h3 className="mt-6 text-xl font-medium text-white">{w.label}</h3>
                  <p className="mt-1 font-display text-lg italic text-brand-300/90">“{w.question}”</p>
                  <ul className="mt-5 flex flex-wrap gap-2">
                    {w.pages.map((p) => (
                      <li key={p.path} title={p.summary} className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.07] bg-ink-950/60 px-2.5 py-1 text-xs text-zinc-400">
                        <p.icon className="w-3 h-3" /> {p.label}
                      </li>
                    ))}
                  </ul>
                </SpotlightCard>
              </Reveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}

const INVARIANTS: { icon: LucideIcon; title: string; body: string }[] = [
  {
    icon: KeyRound,
    title: 'Two keys for real money',
    body: 'A real order needs BINANCE_TESTNET=false and ALLOW_MAINNET_TRADING=true — two independent flags. Out of the box, everything runs on testnet and paper.',
  },
  {
    icon: Lock,
    title: 'The AI gets tools, never the wallet',
    body: 'Agents can read markets and run analysis. Live trading is not exposed to them at all — not as a tool, not over MCP. They may place paper orders only when you enable it.',
  },
  {
    icon: ShieldCheck,
    title: 'Deterministic gates are final',
    body: 'Every AI decision is re-checked with backend arithmetic, and every buy by a risk engine that cannot be overridden. A model can propose; math and explicit flags decide.',
  },
];

function Safety() {
  return (
    <section id="safety" className="scroll-mt-24 relative overflow-hidden border-t border-white/[0.06] py-28">
      <GridBackdrop className="opacity-60" />
      <div className="relative mx-auto grid max-w-[1200px] gap-14 px-6 lg:grid-cols-[1fr_minmax(0,28rem)] lg:items-center">
        <div>
          <SectionHeading
            eyebrow="Safety by construction"
            title={<>Built so a confident model <em className="text-zinc-500">can’t lose your money.</em></>}
          />
          <div className="mt-10 space-y-4">
            {INVARIANTS.map((inv, i) => (
              <Reveal key={inv.title} delay={i * 0.08}>
                <div className="flex gap-5 rounded-2xl border border-white/[0.06] bg-ink-900/60 p-6">
                  <span className="font-mono text-sm text-brand-400">0{i + 1}</span>
                  <div>
                    <h3 className="flex items-center gap-2 text-base font-medium text-white">
                      <inv.icon className="w-4 h-4 text-zinc-400" /> {inv.title}
                    </h3>
                    <p className="mt-2 text-sm leading-relaxed text-zinc-400">{inv.body}</p>
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
        <Reveal delay={0.15}>
          <div className="rounded-3xl border border-white/[0.07] bg-ink-900/70 p-8">
            <DecisionFlow />
          </div>
        </Reveal>
      </div>
    </section>
  );
}

const FIRST_STEPS = [
  { n: '01', title: 'Look at a market', body: 'Open Market Data, pick BTCUSDT, and read the live chart and depth.', path: 'market' },
  { n: '02', title: 'Fund a paper account', body: 'Create a simulated account in Paper Trading. It is play money against real prices.', path: 'paper-trading' },
  { n: '03', title: 'Ask the agent', body: 'Run the AI Agent on a symbol and read its reasoning — and what the validator said.', path: 'agent' },
  { n: '04', title: 'Test before you trust', body: 'Backtest a strategy over stored candles, then stress it in the Research Suite.', path: 'backtest' },
];

function FirstSession() {
  const { isAuthenticated } = useAuth();
  return (
    <section id="start" className="scroll-mt-24 border-t border-white/[0.06] py-28">
      <div className="mx-auto max-w-[1200px] px-6">
        <SectionHeading
          eyebrow="Your first session"
          title={<>Ten minutes to <em className="text-zinc-500">your first decision.</em></>}
          body="New here? Follow these four steps in order. The dashboard shows the same checklist and ticks it off as you go."
        />
        <ol className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FIRST_STEPS.map((s, i) => (
            <Reveal key={s.n} delay={i * 0.06}>
              <Link
                to={isAuthenticated ? appPath(s.path) : '/login?mode=register'}
                className="group flex h-full flex-col rounded-3xl border border-white/[0.07] bg-ink-900/60 p-6 transition hover:border-brand-500/30 hover:bg-ink-850 cursor-pointer"
              >
                <span className="font-display text-5xl text-zinc-700 transition-colors group-hover:text-brand-400">{s.n}</span>
                <h3 className="mt-6 text-base font-medium text-white">{s.title}</h3>
                <p className="mt-2 flex-1 text-sm leading-relaxed text-zinc-400">{s.body}</p>
                <span className="mt-6 inline-flex items-center gap-1 text-xs text-zinc-500 group-hover:text-white">
                  Go <ArrowRight className="w-3 h-3 transition-transform group-hover:translate-x-0.5" />
                </span>
              </Link>
            </Reveal>
          ))}
        </ol>
      </div>
    </section>
  );
}

const FAQS = [
  {
    q: 'Is this real trading?',
    a: 'Not unless you make it so. QuantX defaults to Binance testnet and paper accounts. Real orders require two separate configuration flags and exchange credentials on the server.',
  },
  {
    q: 'Which AI models does it use?',
    a: 'Anthropic Claude when an Anthropic key is configured, otherwise any OpenAI-compatible endpoint — OpenAI, Groq, Gemini, or a local Ollama model.',
  },
  {
    q: 'Can the AI place trades on its own?',
    a: 'Only paper orders, and only when mutations are explicitly enabled. Live trading is never exposed to an agent, every decision passes the validator, and every buy passes the risk engine.',
  },
  {
    q: 'How do I sign in?',
    a: 'With email and password, or with Google or GitHub through OAuth 2.0 (with PKCE) when the server has those providers configured.',
  },
  {
    q: 'Is this financial advice?',
    a: 'No. QuantX is research software. Signals, backtests and simulations describe the past and the model’s view; they are not a promise about the future.',
  },
];

function Faq() {
  return (
    <section id="faq" className="scroll-mt-24 border-t border-white/[0.06] py-28">
      <div className="mx-auto grid max-w-[1200px] gap-12 px-6 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <SectionHeading eyebrow="FAQ" title={<>Questions people <em className="text-zinc-500">actually ask.</em></>} />
        <div className="space-y-3">
          {FAQS.map((f, i) => (
            <div key={f.q} className="d-collapse d-collapse-plus rounded-2xl border border-white/[0.07] bg-ink-900/60">
              <input type="radio" name="faq" defaultChecked={i === 0} aria-label={f.q} />
              <div className="d-collapse-title text-base font-medium text-white">{f.q}</div>
              <div className="d-collapse-content text-sm leading-relaxed text-zinc-400">
                <p>{f.a}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function FinalCta() {
  const { isAuthenticated } = useAuth();
  return (
    <section className="relative overflow-hidden border-t border-white/[0.06] py-28">
      <Spotlight className="-top-60 left-1/4" />
      <GridBackdrop />
      <Reveal className="relative mx-auto max-w-3xl px-6 text-center">
        <Terminal className="mx-auto h-6 w-6 text-brand-400" />
        <h2 className="mt-6 font-display text-[clamp(2.4rem,5vw,4.2rem)] leading-[1.02] text-white">
          Your research desk is <em className="text-brand-400">one click away.</em>
        </h2>
        <p className="mx-auto mt-5 max-w-xl text-zinc-400">
          Paper-first, fully audited, and honest about what it knows. Sign in with Google, GitHub or email.
        </p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
          <Link to={isAuthenticated ? appPath('') : '/login?mode=register'} className="group cursor-pointer">
            <MovingBorderButton>
              {isAuthenticated ? 'Open the terminal' : 'Create a free account'} <ArrowRight className="w-4 h-4" />
            </MovingBorderButton>
          </Link>
          {!isAuthenticated && (
            <Link to="/login" className="text-sm text-zinc-400 hover:text-white cursor-pointer">
              I already have an account
            </Link>
          )}
        </div>
      </Reveal>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-white/[0.06] py-10">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-6 px-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          <Logo />
          <span className="text-xs text-zinc-600">Research software · not financial advice</span>
        </div>
        <ul className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-zinc-500">
          {SECTIONS.map((s) => (
            <li key={s.id}>
              <a href={`#${s.id}`} className="hover:text-white cursor-pointer">{s.label}</a>
            </li>
          ))}
          <li>
            <Link to="/login" className="hover:text-white cursor-pointer">Sign in</Link>
          </li>
        </ul>
      </div>
    </footer>
  );
}

export default function HomePage() {
  useEffect(() => {
    document.title = 'QuantX — Let the agents argue. Let the math decide.';
  }, []);

  return (
    <div className="min-h-screen bg-ink-950">
      <a href="#how-it-works" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:text-ink-950">
        Skip to content
      </a>
      <SiteNav />
      <main>
        <Hero />
        <CapabilityStrip />
        <HowItWorks />
        <PlatformMap />
        <Safety />
        <FirstSession />
        <Faq />
        <FinalCta />
      </main>
      <Footer />
    </div>
  );
}
