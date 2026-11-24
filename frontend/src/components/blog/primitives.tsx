import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Check, ChevronDown, ChevronRight, Copy, ListTree } from 'lucide-react';

export interface TocEntry {
  id: string;
  label: string;
  children?: { id: string; label: string }[];
}

/** Distance from the top of the viewport at which a heading counts as "current". */
const ACTIVE_OFFSET = 140;

/**
 * The id of the last heading that has scrolled past the reading line.
 * Recomputed once per animation frame while scrolling, which is cheaper and
 * steadier than one IntersectionObserver callback per heading.
 */
function useActiveHeading(ids: string[]): string {
  const [active, setActive] = useState(ids[0] ?? '');

  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      let current = ids[0] ?? '';
      for (const id of ids) {
        const el = document.getElementById(id);
        if (!el) continue;
        if (el.getBoundingClientRect().top - ACTIVE_OFFSET <= 0) current = id;
        else break;
      }
      const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
      if (atBottom && ids.length) current = ids[ids.length - 1];
      setActive(current);
    };
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [ids]);

  return active;
}

function TocLinks({
  entries,
  active,
  activeParent,
  onNavigate,
}: {
  entries: TocEntry[];
  active: string;
  activeParent: string;
  onNavigate?: () => void;
}) {
  return (
    <ol className="space-y-0.5 border-l border-white/[0.07]">
      {entries.map((entry, i) => {
        const isParent = entry.id === activeParent;
        const isExact = entry.id === active;
        return (
          <li key={entry.id}>
            <a
              href={`#${entry.id}`}
              onClick={onNavigate}
              aria-current={isExact ? 'location' : undefined}
              className={`-ml-px flex gap-2.5 border-l py-1.5 pl-4 pr-2 text-[13px] leading-snug transition-colors ${
                isParent
                  ? 'border-brand-400 text-white'
                  : 'border-transparent text-zinc-500 hover:border-white/20 hover:text-zinc-200'
              }`}
            >
              <span className={`font-mono text-[11px] tabular-nums ${isParent ? 'text-brand-400' : 'text-zinc-600'}`}>
                {String(i + 1).padStart(2, '0')}
              </span>
              <span>{entry.label}</span>
            </a>
            {entry.children && entry.children.length > 0 && (
              <ol className="mb-1 space-y-0.5">
                {entry.children.map((child) => {
                  const on = child.id === active;
                  return (
                    <li key={child.id}>
                      <a
                        href={`#${child.id}`}
                        onClick={onNavigate}
                        aria-current={on ? 'location' : undefined}
                        className={`-ml-px block border-l py-1 pl-[2.6rem] pr-2 text-[12.5px] leading-snug transition-colors ${
                          on
                            ? 'border-brand-400/70 text-brand-200'
                            : 'border-transparent text-zinc-500 hover:text-zinc-300'
                        }`}
                      >
                        {child.label}
                      </a>
                    </li>
                  );
                })}
              </ol>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/**
 * Contents navigation with scroll-spy. On large screens it is a sticky
 * sidebar; below that it collapses into a bar that names the current section
 * and opens the full list on demand.
 */
export function TableOfContents({ entries }: { entries: TocEntry[] }) {
  const ids = useMemo(() => entries.flatMap((e) => [e.id, ...(e.children ?? []).map((c) => c.id)]), [entries]);
  const active = useActiveHeading(ids);
  const [open, setOpen] = useState(false);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLElement>(null);

  // The full list can be taller than the viewport. Scroll the list itself
  // (never the window) so the current entry stays in view as the reader moves.
  useEffect(() => {
    for (const box of [sidebarRef.current, panelRef.current]) {
      const link = box?.querySelector<HTMLElement>(`a[href="#${CSS.escape(active)}"]`);
      if (!box || !link || box.clientHeight === 0) continue;
      const b = box.getBoundingClientRect();
      const l = link.getBoundingClientRect();
      const margin = 48;
      if (l.top < b.top + margin) box.scrollBy({ top: l.top - b.top - margin, behavior: 'smooth' });
      else if (l.bottom > b.bottom - margin) box.scrollBy({ top: l.bottom - b.bottom + margin, behavior: 'smooth' });
    }
  }, [active, open]);

  const parent =
    entries.find((e) => e.id === active || e.children?.some((c) => c.id === active)) ?? entries[0];
  const child = parent?.children?.find((c) => c.id === active);
  const parentIndex = parent ? entries.indexOf(parent) : 0;

  return (
    <>
      {/* Mobile and tablet: a compact bar under the site header. */}
      <div className="sticky top-16 z-30 -mx-4 border-b border-white/[0.06] bg-ink-950/90 px-4 backdrop-blur-xl lg:hidden">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-controls="blog-toc-mobile"
          className="flex w-full items-center gap-3 py-3 text-left cursor-pointer"
        >
          <ListTree className="h-4 w-4 shrink-0 text-brand-400" />
          <span className="min-w-0 flex-1 truncate text-sm text-zinc-300">
            <span className="font-mono text-xs text-brand-400">{String(parentIndex + 1).padStart(2, '0')}</span>{' '}
            {parent?.label}
            {child && <span className="text-zinc-500"> · {child.label}</span>}
          </span>
          <ChevronDown className={`h-4 w-4 shrink-0 text-zinc-500 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
        {open && (
          <nav ref={panelRef} id="blog-toc-mobile" aria-label="Contents" className="max-h-[60vh] overflow-y-auto pb-4">
            <TocLinks entries={entries} active={active} activeParent={parent?.id ?? ''} onNavigate={() => setOpen(false)} />
          </nav>
        )}
      </div>

      {/* Desktop: sticky sidebar. */}
      <nav aria-label="Contents" className="hidden lg:block">
        <div ref={sidebarRef} className="sticky top-24 max-h-[calc(100vh-7rem)] overflow-y-auto pb-10 pr-2">
          <p className="mb-4 font-mono text-[11px] uppercase tracking-[0.2em] text-zinc-500">Contents</p>
          <TocLinks entries={entries} active={active} activeParent={parent?.id ?? ''} />
        </div>
      </nav>
    </>
  );
}

/** A labelled figure. `kind` makes it obvious whether the reader is looking at the product or a drawing. */
export function Figure({
  kind,
  caption,
  children,
  scroll = false,
}: {
  kind: 'Screenshot' | 'Diagram' | 'Illustration';
  caption: ReactNode;
  children: ReactNode;
  /** Wide drawings scroll sideways on small screens instead of shrinking to unreadable text. */
  scroll?: boolean;
}) {
  return (
    <figure className="my-10">
      <div className="overflow-hidden rounded-2xl border border-white/[0.08] bg-ink-900/60 shadow-card">
        {scroll ? <div className="overflow-x-auto p-3 sm:p-5">{children}</div> : children}
      </div>
      <figcaption className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[13px] leading-relaxed text-zinc-500">
        <span
          className={`rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] ring-1 ring-inset ${
            kind === 'Screenshot' ? 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/25' : 'bg-brand-500/10 text-brand-300 ring-brand-500/25'
          }`}
        >
          {kind}
        </span>
        <span className="min-w-0 flex-1">{caption}</span>
        {scroll && <span className="w-full font-mono text-[11px] text-zinc-600 lg:hidden">Scroll sideways to see all of it →</span>}
      </figcaption>
    </figure>
  );
}

/** A real product screenshot with fixed dimensions, so the page never jumps while it loads. */
export function Screenshot({ src, alt, caption }: { src: string; alt: string; caption: ReactNode }) {
  return (
    <Figure kind="Screenshot" caption={caption}>
      <img
        src={src}
        alt={alt}
        width={1600}
        height={975}
        loading="lazy"
        decoding="async"
        className="block aspect-[1600/975] h-auto w-full"
      />
    </Figure>
  );
}

/** Monospaced code with a language label and a copy button. */
export function CodeBlock({ label, code }: { label: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard access can be refused (insecure origin, permissions); the code stays selectable.
    }
  };

  return (
    <div className="my-6 overflow-hidden rounded-2xl border border-white/[0.08] bg-ink-950/80">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-2">
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-zinc-500">{label}</span>
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] text-zinc-500 transition-colors hover:bg-white/5 hover:text-zinc-200 cursor-pointer"
          aria-label={`Copy ${label}`}
        >
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="overflow-x-auto px-4 py-4 font-mono text-[12.5px] leading-relaxed text-zinc-200">
        <code>{code}</code>
      </pre>
    </div>
  );
}

/**
 * Optional depth. The main text stays readable for a first-time reader; the
 * full technical version sits behind this, closed by default.
 */
export function Details({ summary, children }: { summary: string; children: ReactNode }) {
  return (
    <details className="group my-8 rounded-2xl border border-white/[0.08] bg-ink-900/40 open:bg-ink-900/60">
      <summary className="flex cursor-pointer list-none items-center gap-3 rounded-2xl px-5 py-4 text-[15px] font-medium text-zinc-200 transition-colors hover:text-white [&::-webkit-details-marker]:hidden">
        <ChevronRight className="h-4 w-4 shrink-0 text-brand-400 transition-transform group-open:rotate-90" />
        <span className="min-w-0 flex-1">{summary}</span>
        <span className="hidden shrink-0 rounded-full border border-white/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-zinc-500 sm:inline">
          <span className="group-open:hidden">Technical details</span>
          <span className="hidden group-open:inline">Hide</span>
        </span>
      </summary>
      <div className="border-t border-white/[0.06] px-5 pb-6 pt-1">{children}</div>
    </details>
  );
}

/** A highlighted aside. `tone` follows the app's semantic colours. */
export function Callout({
  title,
  children,
  tone = 'info',
}: {
  title: string;
  children: ReactNode;
  tone?: 'info' | 'warning' | 'safe';
}) {
  const toneClass = {
    info: 'border-brand-500/25 bg-brand-500/[0.05]',
    warning: 'border-yellow-500/25 bg-yellow-500/[0.05]',
    safe: 'border-emerald-500/25 bg-emerald-500/[0.05]',
  }[tone];
  const titleClass = { info: 'text-brand-300', warning: 'text-yellow-300', safe: 'text-emerald-300' }[tone];
  return (
    <aside className={`my-6 rounded-2xl border px-5 py-4 ${toneClass}`}>
      <p className={`text-sm font-medium ${titleClass}`}>{title}</p>
      <div className="mt-1.5 text-sm leading-relaxed text-zinc-300">{children}</div>
    </aside>
  );
}
