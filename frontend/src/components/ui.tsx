import React from 'react';
import { AlertCircle, Inbox, Loader2, RefreshCw } from 'lucide-react';

/** Page heading with optional description and right-aligned actions. */
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
    <div className="flex items-start justify-between gap-4">
      <div>
        <h2 className="text-2xl font-bold text-white">{title}</h2>
        {description && <p className="text-sm text-slate-400 mt-1">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}

/** Bordered panel used for every content block. */
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
    <div className={`rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden ${className}`}>
      {(title || actions) && (
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between gap-4">
          {title && (
            <h3 className="text-base font-semibold text-white flex items-center gap-2">
              {icon}
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

/** Single metric tile. */
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
  const toneClass = {
    neutral: 'text-slate-400',
    positive: 'text-emerald-400',
    negative: 'text-red-400',
    warning: 'text-amber-400',
  }[tone];

  return (
    <div className="p-5 rounded-xl bg-slate-900/50 border border-slate-800">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">{label}</span>
        {icon && <span className="text-slate-600">{icon}</span>}
      </div>
      <div className="text-2xl font-bold text-white font-mono">{value}</div>
      {sub !== undefined && sub !== null && (
        <div className={`mt-1 text-xs font-medium ${toneClass}`}>{sub}</div>
      )}
    </div>
  );
}

/** Coloured pill for statuses and actions. */
export function Badge({
  children,
  tone = 'neutral',
}: {
  children: React.ReactNode;
  tone?: 'neutral' | 'positive' | 'negative' | 'warning' | 'info';
}) {
  const toneClass = {
    neutral: 'bg-slate-500/10 text-slate-300 border-slate-500/20',
    positive: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    negative: 'bg-red-500/10 text-red-400 border-red-500/20',
    warning: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    info: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
  }[tone];

  return (
    <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${toneClass}`}>
      {children}
    </span>
  );
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-slate-500 text-sm">
      <Loader2 className="w-4 h-4 animate-spin" />
      {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 px-5 text-center">
      <AlertCircle className="w-6 h-6 text-red-400" />
      <p className="text-sm text-red-300 max-w-lg">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-cyan-400 transition-colors"
        >
          <RefreshCw className="w-3 h-3" /> Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ message, hint }: { message: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 px-5 text-center">
      <Inbox className="w-6 h-6 text-slate-600" />
      <p className="text-sm text-slate-400">{message}</p>
      {hint && <p className="text-xs text-slate-600 max-w-md">{hint}</p>}
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
    primary: 'bg-cyan-600 hover:bg-cyan-500 text-white border-cyan-500',
    secondary: 'bg-slate-800 hover:bg-slate-700 text-slate-200 border-slate-700',
    danger: 'bg-red-600 hover:bg-red-500 text-white border-red-500',
  }[variant];

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`px-3.5 py-1.5 rounded-lg border text-xs font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${variantClass} ${className}`}
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
      <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">{label}</span>
      {children}
    </label>
  );
}

const inputClass =
  'px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-sm text-white font-mono ' +
  'focus:outline-none focus:border-cyan-600 transition-colors disabled:opacity-40';

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
      className={`px-5 py-2.5 text-xs font-medium text-slate-500 uppercase tracking-wider whitespace-nowrap ${
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
