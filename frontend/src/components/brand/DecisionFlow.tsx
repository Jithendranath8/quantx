import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Bot, Calculator, CheckCircle2, FileCheck2, ShieldCheck } from 'lucide-react';

// An illustrative walk through one decision. The numbers are examples, never
// market data, and the panel says so.
const STAGES = [
  { icon: Bot, title: 'Agents propose', detail: 'BUY BTCUSDT · confidence 0.72', note: 'Market, technical, quant and risk specialists debate the setup.' },
  { icon: Calculator, title: 'Validator re-checks', detail: 'Stop below entry · R:R 2.1 ✓', note: 'Prices, stops and sizing are recomputed with plain arithmetic.' },
  { icon: ShieldCheck, title: 'Risk engine gates', detail: 'Exposure 4.2% of 10% limit ✓', note: 'Every buy must pass hard limits the model cannot override.' },
  { icon: FileCheck2, title: 'Paper order + audit', detail: 'Filled with slippage & fees', note: 'Every step lands in the immutable event ledger.' },
];

export default function DecisionFlow({ interval = 2600 }: { interval?: number }) {
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const id = window.setInterval(() => setStep((s) => (s + 1) % STAGES.length), interval);
    return () => window.clearInterval(id);
  }, [interval]);

  return (
    <div className="relative w-full max-w-md">
      <div className="flex items-center justify-between mb-4">
        <span className="text-[11px] font-mono uppercase tracking-[0.18em] text-zinc-500">One decision, four gates</span>
        <span className="text-[10px] font-mono text-zinc-600">illustration</span>
      </div>
      <ol className="relative space-y-3">
        {/* Rail connecting the stages, filled up to the current one. */}
        <span className="absolute left-[19px] top-5 bottom-5 w-px bg-white/[0.07]" aria-hidden="true" />
        <motion.span
          className="absolute left-[19px] top-5 bottom-5 w-px origin-top bg-gradient-to-b from-brand-400 to-brand-600"
          animate={{ scaleY: step / (STAGES.length - 1) }}
          transition={{ duration: 0.6, ease: 'easeInOut' }}
          aria-hidden="true"
        />
        {STAGES.map((s, i) => {
          const done = i < step;
          const active = i === step;
          const Icon = done ? CheckCircle2 : s.icon;
          return (
            <li key={s.title} className="relative flex gap-4">
              <span
                className={`relative z-10 grid place-items-center w-10 h-10 shrink-0 rounded-xl ring-1 ring-inset transition-colors duration-500 ${
                  active
                    ? 'bg-brand-500/15 text-brand-300 ring-brand-400/40 shadow-glow-sm'
                    : done
                      ? 'bg-emerald-500/10 text-emerald-400 ring-emerald-500/25'
                      : 'bg-ink-850 text-zinc-500 ring-white/[0.07]'
                }`}
              >
                <Icon className="w-4 h-4" />
              </span>
              <div
                className={`flex-1 rounded-xl border px-4 py-3 transition-colors duration-500 ${
                  active ? 'border-brand-500/25 bg-ink-850/90' : 'border-white/[0.05] bg-ink-900/40'
                }`}
              >
                <p className={`text-sm font-medium ${active || done ? 'text-white' : 'text-zinc-400'}`}>{s.title}</p>
                <p className="font-mono text-xs text-zinc-500 mt-0.5">{s.detail}</p>
                <AnimatePresence initial={false}>
                  {active && (
                    <motion.p
                      className="text-xs text-zinc-400 overflow-hidden"
                      initial={{ height: 0, opacity: 0, marginTop: 0 }}
                      animate={{ height: 'auto', opacity: 1, marginTop: 6 }}
                      exit={{ height: 0, opacity: 0, marginTop: 0 }}
                    >
                      {s.note}
                    </motion.p>
                  )}
                </AnimatePresence>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
