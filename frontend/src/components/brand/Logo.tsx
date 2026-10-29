import { useId } from 'react';
import { Link } from 'react-router-dom';

/**
 * QuantX mark — the Breakout Q. The Q's tail is a price line: it leaves the
 * bowl, turns once, and breaks out to a live signal point.
 * Source of truth: brand/quantx-mark.svg.
 */
export function LogoMark({ className = 'w-8 h-8' }: { className?: string }) {
  // Unique ids so several marks on one page never share masks or gradients.
  const id = useId().replace(/:/g, '');
  const tail = 'M 240 286 L 318 364 L 424 240';
  return (
    <svg viewBox="0 0 512 512" className={className} aria-hidden="true">
      <defs>
        <linearGradient id={`${id}t`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#1c1e24" />
          <stop offset="1" stopColor="#0a0b0e" />
        </linearGradient>
        <radialGradient id={`${id}g`} cx="424" cy="240" r="190" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#ff7a1a" stopOpacity="0.3" />
          <stop offset="1" stopColor="#ff7a1a" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`${id}r`} x1="0" y1="110" x2="0" y2="402" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#d4d4d8" />
        </linearGradient>
        <linearGradient id={`${id}s`} x1="240" y1="364" x2="424" y2="240" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#c94a0b" />
          <stop offset="0.5" stopColor="#ff7a1a" />
          <stop offset="1" stopColor="#ffb070" />
        </linearGradient>
        <mask id={`${id}m`} maskUnits="userSpaceOnUse" x="0" y="0" width="512" height="512">
          <rect width="512" height="512" fill="#fff" />
          <path d={tail} fill="none" stroke="#000" strokeWidth="70" strokeLinecap="round" strokeLinejoin="round" />
        </mask>
      </defs>
      <rect width="512" height="512" rx="116" fill={`url(#${id}t)`} />
      <rect width="512" height="512" rx="116" fill={`url(#${id}g)`} />
      <rect x="3" y="3" width="506" height="506" rx="113" fill="none" stroke="#fff" strokeOpacity="0.07" strokeWidth="6" />
      <circle cx="212" cy="256" r="124" fill="none" stroke={`url(#${id}r)`} strokeWidth="44" mask={`url(#${id}m)`} />
      <path d={tail} fill="none" stroke={`url(#${id}s)`} strokeWidth="38" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="424" cy="240" r="40" fill="#ffb070" opacity="0.18" />
      <circle cx="424" cy="240" r="24" fill="#ffe2c7" />
    </svg>
  );
}

export function Logo({ to = '/', compact = false }: { to?: string; compact?: boolean }) {
  return (
    <Link to={to} className="flex items-center gap-2.5 shrink-0 cursor-pointer" aria-label="QuantX home">
      <LogoMark />
      {!compact && (
        <span className="text-[15px] font-semibold tracking-tight text-white">
          Quant<span className="text-brand-400">X</span>
        </span>
      )}
    </Link>
  );
}
