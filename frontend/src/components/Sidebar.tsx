import { NavLink } from 'react-router-dom';
import {
  BookOpen, Bot, Cpu, FlaskConical, History, LayoutDashboard,
  Layers, LineChart, ListOrdered, PieChart, Settings, Shield, Terminal, TrendingUp, Wallet, Zap,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import api from '../lib/api';
import { useApi, usePolling } from '../lib/useApi';
import type { SystemHealth } from '../lib/types';

interface NavItem {
  to: string;
  icon: LucideIcon;
  label: string;
}

// Grouped so 17 destinations read as a few scannable sections rather than one
// long flat list.
const navGroups: { heading: string; items: NavItem[] }[] = [
  {
    heading: 'Overview',
    items: [{ to: '/', icon: LayoutDashboard, label: 'Dashboard' }],
  },
  {
    heading: 'Markets',
    items: [
      { to: '/market', icon: TrendingUp, label: 'Market Data' },
      { to: '/indicators', icon: LineChart, label: 'Indicators' },
      { to: '/positions', icon: Layers, label: 'Positions' },
      { to: '/orders', icon: ListOrdered, label: 'Orders' },
    ],
  },
  {
    heading: 'Trading',
    items: [
      { to: '/strategies', icon: Cpu, label: 'Strategies' },
      { to: '/paper-trading', icon: Wallet, label: 'Paper Trading' },
      { to: '/live', icon: Zap, label: 'Live Trading' },
      { to: '/risk', icon: Shield, label: 'Risk Engine' },
    ],
  },
  {
    heading: 'Research & AI',
    items: [
      { to: '/agent', icon: Bot, label: 'AI Agent' },
      { to: '/backtest', icon: History, label: 'Backtesting' },
      { to: '/experiments', icon: FlaskConical, label: 'Research' },
    ],
  },
  {
    heading: 'Insights',
    items: [
      { to: '/journal', icon: BookOpen, label: 'Trade Journal' },
      { to: '/analytics', icon: PieChart, label: 'Analytics' },
    ],
  },
  {
    heading: 'System',
    items: [
      { to: '/logs', icon: Terminal, label: 'Event Ledger' },
      { to: '/settings', icon: Settings, label: 'Settings' },
    ],
  },
];

/** Footer status, driven by the real health endpoint. */
function SystemStatus() {
  const health = useApi<SystemHealth>(
    () => api.get<SystemHealth>('/health/system').then((r) => r.data),
  );
  usePolling(() => health.reload(), 60_000);

  const { label, dot } = health.error
    ? { label: 'Status unavailable', dot: 'bg-slate-500' }
    : health.data?.status === 'HEALTHY'
      ? { label: 'System operational', dot: 'bg-emerald-400 animate-pulse' }
      : health.data?.status === 'DEGRADED'
        ? { label: 'System degraded', dot: 'bg-amber-400 animate-pulse' }
        : health.data
          ? { label: 'System unhealthy', dot: 'bg-red-400 animate-pulse' }
          : { label: 'Checking…', dot: 'bg-slate-600' };

  return (
    <div className="flex items-center gap-2 rounded-lg px-2.5 py-2 ring-1 ring-inset ring-white/[0.06] bg-white/[0.02]">
      <span className="relative flex h-2 w-2">
        <span className={`absolute inline-flex h-full w-full rounded-full ${dot} opacity-60`} />
        <span className={`relative inline-flex h-2 w-2 rounded-full ${dot}`} />
      </span>
      <span className="text-xs text-slate-400">{label}</span>
    </div>
  );
}

export default function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 h-screen w-64 border-r hairline bg-slate-950/70 backdrop-blur-xl flex flex-col z-40">
      <div className="px-5 py-5 flex items-center gap-3 border-b hairline">
        <div className="relative w-10 h-10 rounded-xl bg-brand-gradient grid place-items-center font-bold text-white text-lg shadow-glow-sm">
          QX
        </div>
        <div>
          <h1 className="font-bold text-base leading-none tracking-tight text-white">QuantX</h1>
          <p className="text-[10px] text-slate-500 font-mono mt-1 tracking-wider">TRADING PLATFORM</p>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-5">
        {navGroups.map((group) => (
          <div key={group.heading}>
            <p className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-600">
              {group.heading}
            </p>
            <div className="space-y-0.5">
              {group.items.map(({ to, icon: Icon, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  className={({ isActive }) =>
                    `group relative flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                      isActive
                        ? 'text-white bg-cyan-500/[0.12] ring-1 ring-inset ring-cyan-400/20'
                        : 'text-slate-400 hover:text-slate-100 hover:bg-white/[0.04]'
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-1 rounded-r-full bg-brand-gradient" />
                      )}
                      <Icon
                        className={`w-4 h-4 flex-shrink-0 transition-colors ${
                          isActive ? 'text-cyan-400' : 'text-slate-500 group-hover:text-slate-300'
                        }`}
                      />
                      {label}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="px-3 py-3 border-t hairline">
        <SystemStatus />
      </div>
    </aside>
  );
}
