import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { CornerDownLeft, Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { ALL_PAGES, appPath } from '../../lib/navigation';

/** ⌘K launcher: jump to any page by name or by what it does. */
export default function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return ALL_PAGES;
    return ALL_PAGES.filter((p) =>
      `${p.label} ${p.summary} ${p.workspace}`.toLowerCase().includes(q),
    );
  }, [query]);

  useEffect(() => {
    if (!open) return;
    setQuery('');
    setActive(0);
    // Focus after the enter animation has mounted the input.
    const id = window.setTimeout(() => inputRef.current?.focus(), 20);
    return () => window.clearTimeout(id);
  }, [open]);

  const go = (index: number) => {
    const page = results[index];
    if (!page) return;
    navigate(appPath(page.path));
    onClose();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      go(active);
    } else if (e.key === 'Escape') {
      onClose();
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[60] flex items-start justify-center px-4 pt-[12vh]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          <button
            type="button"
            aria-label="Close command palette"
            className="absolute inset-0 bg-black/60 backdrop-blur-sm cursor-default"
            onClick={onClose}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Go to page"
            className="relative w-full max-w-xl overflow-hidden rounded-2xl border border-white/10 bg-ink-900/95 shadow-2xl"
            initial={{ y: -12, scale: 0.98 }}
            animate={{ y: 0, scale: 1 }}
            exit={{ y: -8, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 420, damping: 32 }}
            onKeyDown={onKeyDown}
          >
            <div className="flex items-center gap-3 border-b border-white/[0.07] px-4">
              <Search className="w-4 h-4 text-zinc-500" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setActive(0);
                }}
                placeholder="Search pages — try “backtest” or “risk”"
                className="h-12 w-full bg-transparent text-sm text-white placeholder:text-zinc-500 focus:outline-none"
                aria-label="Search pages"
              />
              <kbd className="d-kbd d-kbd-sm bg-white/5 border-white/10 text-zinc-400">esc</kbd>
            </div>
            <ul className="max-h-[50vh] overflow-y-auto p-2" role="listbox">
              {results.length === 0 && (
                <li className="px-3 py-8 text-center text-sm text-zinc-500">No page matches “{query}”.</li>
              )}
              {results.map((p, i) => {
                const Icon = p.icon;
                const selected = i === active;
                return (
                  <li key={p.path} role="option" aria-selected={selected}>
                    <button
                      type="button"
                      onMouseEnter={() => setActive(i)}
                      onClick={() => go(i)}
                      className={`w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-left cursor-pointer transition-colors ${
                        selected ? 'bg-white/[0.06]' : ''
                      }`}
                    >
                      <span
                        className={`grid place-items-center w-8 h-8 rounded-lg ring-1 ring-inset ${
                          selected ? 'bg-brand-500/15 text-brand-300 ring-brand-500/30' : 'bg-white/[0.03] text-zinc-400 ring-white/[0.06]'
                        }`}
                      >
                        <Icon className="w-4 h-4" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm text-white">{p.label}</span>
                        <span className="block truncate text-xs text-zinc-500">{p.summary}</span>
                      </span>
                      <span className="text-[10px] uppercase tracking-wider text-zinc-600">{p.workspace}</span>
                      {selected && <CornerDownLeft className="w-3.5 h-3.5 text-zinc-500" />}
                    </button>
                  </li>
                );
              })}
            </ul>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
