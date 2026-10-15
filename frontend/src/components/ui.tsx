import React from 'react';
import { AlertCircle, Inbox, Loader2, RefreshCw } from 'lucide-react';

/** Page heading with an accent eyebrow, optional description and right-aligned actions. */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 animate-fade-in-up">
      <div className="min-w-0">
        <div className="flex items-center gap-2.5">
          <span className="h-5 w-1 rounded-full bg-brand-gradient" />
          <h2 className="text-2xl font-bold text-white">{title}</h2>
        </div>
        {description && <p className="text-sm text-slate-400 mt-1.5 pl-3.5">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}

/** Elevated, frosted panel used for every content block. */
export function Card({
  title,
  icon,
  actions,
  children,
  className = '',
}: {
  title?: string;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`glass rounded-2xl overflow-hidden transition-shadow duration-300 hover:shadow-card-hover ${className}`}
    >
      {(title || actions) && (
        <div className="px-5 py-3.5 border-b hairline flex items-center justify-between gap-4">
          {title && (
            <h3 className="text-sm font-semibold text-white flex items-center gap-2.5">
              {icon && (
                <span className="grid place-items-center w-7 h-7 rounded-lg bg-cyan-500/10 text-cyan-400 ring-1 ring-inset ring-cyan-500/20">
                  {icon}
                </span>
              )}
              {title}
            </h3>
          )}
          {actions}
        </div>
      )}
      {children}
    </div>
  );
}

const TONE_TEXT = {
  neutral: 'text-slate-400',
  positive: 'text-emerald-400',
  negative: 'text-red-400',
  warning: 'text-amber-400',
} as const;

const TONE_CHIP = {
  neutral: 'bg-slate-500/10 text-slate-300 ring-slate-400/20',
  positive: 'bg-emerald-500/10 text-emerald-400 ring-emerald-500/25',
  negative: 'bg-red-500/10 text-red-400 ring-red-500/25',
  warning: 'bg-amber-500/10 text-amber-400 ring-amber-500/25',
} as const;

const TONE_BAR = {
  neutral: 'from-slate-500/0 to-slate-500/0',
  positive: 'from-emerald-500/60 to-emerald-500/0',
  negative: 'from-red-500/60 to-red-500/0',
  warning: 'from-amber-500/60 to-amber-500/0',
} as const;

/** Single metric tile with a tone-coloured accent and icon chip. */
export function StatTile({
  label,
  value,
  sub,
  tone = 'neutral',
  icon,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: 'neutral' | 'positive' | 'negative' | 'warning';
  icon?: React.ReactNode;
}) {
  return (
    <div className="group relative glass rounded-2xl p-5 overflow-hidden transition-all duration-300 hover:shadow-card-hover hover:-translate-y-0.5">
      {/* tone accent along the top edge */}
      <span className={`absolute inset-x-0 top-0 h-px bg-gradient-to-r ${TONE_BAR[tone]}`} />
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{label}</span>
        {icon && (
          <span className={`grid place-items-center w-8 h-8 rounded-lg ring-1 ring-inset ${TONE_CHIP[tone]}`}>
            {icon}
          </span>
        )}
      </div>
      <div className="text-[1.65rem] leading-none font-bold text-white font-mono">{value}</div>
      {sub !== undefined && sub !== null && (
        <div className={`mt-2 text-xs font-medium ${TONE_TEXT[tone]}`}>{sub}</div>
      )}
    </div>
  );
}

/** Coloured pill for statuses and actions, with a leading status dot. */
export function Badge({
  children,
  tone = 'neutral',
}: {
  children: React.ReactNode;
  tone?: 'neutral' | 'positive' | 'negative' | 'warning' | 'info';
}) {
  const toneClass = {
    neutral: 'bg-slate-500/10 text-slate-300 ring-slate-500/20',
    positive: 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/25',
    negative: 'bg-red-500/10 text-red-300 ring-red-500/25',
    warning: 'bg-amber-500/10 text-amber-300 ring-amber-500/25',
    info: 'bg-cyan-500/10 text-cyan-300 ring-cyan-500/25',
  }[tone];
  const dotClass = {
    neutral: 'bg-slate-400',
    positive: 'bg-emerald-400',
    negative: 'bg-red-400',
    warning: 'bg-amber-400',
    info: 'bg-cyan-400',
  }[tone];

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold ring-1 ring-inset ${toneClass}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${dotClass}`} />
      {children}
    </span>
  );
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-14 text-slate-500 text-sm">
      <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
      {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-14 px-5 text-center">
      <span className="grid place-items-center w-11 h-11 rounded-xl bg-red-500/10 ring-1 ring-inset ring-red-500/20">
        <AlertCircle className="w-5 h-5 text-red-400" />
      </span>
      <p className="text-sm text-red-300 max-w-lg">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-cyan-400 transition-colors"
        >
          <RefreshCw className="w-3 h-3" /> Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ message, hint }: { message: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-14 px-5 text-center">
      <span className="grid place-items-center w-11 h-11 rounded-xl bg-slate-500/10 ring-1 ring-inset ring-slate-500/15">
        <Inbox className="w-5 h-5 text-slate-500" />
      </span>
      <p className="text-sm text-slate-300">{message}</p>
      {hint && <p className="text-xs text-slate-500 max-w-md">{hint}</p>}
    </div>
  );
}

/**
 * Render the right thing for an async result.
 *
 * Loading, error and empty are all distinct states. Collapsing them (rendering
 * an empty table for a failed request, say) is how a broken backend ends up
 * looking like a user with no data.
 */
export function AsyncSection<T>({
  state,
  children,
  emptyWhen,
  emptyMessage = 'No data yet',
  emptyHint,
  loadingLabel,
}: {
  state: { data: T | null; loading: boolean; error: string | null; reload: () => void };
  children: (data: T) => React.ReactNode;
  emptyWhen?: (data: T) => boolean;
  emptyMessage?: string;
  emptyHint?: string;
  loadingLabel?: string;
}) {
  if (state.loading && state.data === null) return <LoadingState label={loadingLabel} />;
  if (state.error) return <ErrorState message={state.error} onRetry={state.reload} />;
  if (state.data === null) return <EmptyState message={emptyMessage} hint={emptyHint} />;
  if (emptyWhen?.(state.data)) return <EmptyState message={emptyMessage} hint={emptyHint} />;
  return <>{children(state.data)}</>;
}

export function Button({
  children,
  onClick,
  disabled,
  variant = 'primary',
  type = 'button',
  className = '',
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: 'primary' | 'secondary' | 'danger';
  type?: 'button' | 'submit';
  className?: string;
}) {
  const variantClass = {
    primary:
      'text-white bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 ' +
      'shadow-lg shadow-cyan-600/20 hover:shadow-glow-sm',
    secondary:
      'text-slate-200 bg-white/[0.04] hover:bg-white/[0.08] ring-1 ring-inset ring-white/10 hover:ring-white/20',
    danger:
      'text-white bg-gradient-to-r from-red-500 to-rose-600 hover:from-red-400 hover:to-rose-500 shadow-lg shadow-red-600/20',
  }[variant];

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={
        'px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all duration-200 ' +
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 ' +
        `disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none ${variantClass} ${className}`
      }
    >
      {children}
    </button>
  );
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{label}</span>
      {children}
    </label>
  );
}

const inputClass =
  'px-3 py-1.5 rounded-lg bg-slate-950/60 ring-1 ring-inset ring-white/10 text-sm text-white font-mono ' +
  'placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-cyan-500/60 transition-shadow ' +
  'disabled:opacity-40';

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputClass} ${props.className ?? ''}`} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${inputClass} ${props.className ?? ''}`} />;
}

export function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`${inputClass} font-sans ${props.className ?? ''}`} />;
}

/** Horizontally scrollable table wrapper, so wide tables never break layout. */
export function TableWrap({ children }: { children: React.ReactNode }) {
  return <div className="overflow-x-auto">{children}</div>;
}

export function Th({ children, align = 'left' }: { children?: React.ReactNode; align?: 'left' | 'right' }) {
  return (
    <th
      className={`px-5 py-2.5 text-[11px] font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap ${
        align === 'right' ? 'text-right' : 'text-left'
      }`}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  align = 'left',
  mono = false,
  className = '',
}: {
  children?: React.ReactNode;
  align?: 'left' | 'right';
  mono?: boolean;
  className?: string;
}) {
  return (
    <td
      className={`px-5 py-3 text-sm whitespace-nowrap ${align === 'right' ? 'text-right' : 'text-left'} ${
        mono ? 'font-mono' : ''
      } ${className}`}
    >
      {children}
    </td>
  );
}
