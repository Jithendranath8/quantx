import { NavLink } from 'react-router-dom';
import {
  Activity, BookOpen, Bot, Cpu, FlaskConical, History, LayoutDashboard,
  Layers, LineChart, ListOrdered, PieChart, Settings, Shield, Terminal, TrendingUp, Wallet, Zap,
} from 'lucide-react';

import api from '../lib/api';
import { useApi, usePolling } from '../lib/useApi';
import type { SystemHealth } from '../lib/types';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/market', icon: TrendingUp, label: 'Market Data' },
  { to: '/positions', icon: Layers, label: 'Positions' },
  { to: '/orders', icon: ListOrdered, label: 'Orders' },
  { to: '/indicators', icon: LineChart, label: 'Indicators' },
  { to: '/strategies', icon: Cpu, label: 'Strategies' },
  { to: '/agent', icon: Bot, label: 'AI Agent' },
  { to: '/risk', icon: Shield, label: 'Risk Engine' },
  { to: '/paper-trading', icon: Wallet, label: 'Paper Trading' },
  { to: '/backtest', icon: History, label: 'Backtesting' },
  { to: '/experiments', icon: FlaskConical, label: 'Research' },
  { to: '/journal', icon: BookOpen, label: 'Trade Journal' },
  { to: '/live', icon: Zap, label: 'Live Trading' },
  { to: '/analytics', icon: PieChart, label: 'Analytics' },
  { to: '/health', icon: Activity, label: 'Health Center' },
  { to: '/logs', icon: Terminal, label: 'Event Ledger' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

/** Footer status dot, driven by the real health endpoint. */
function SystemStatus() {
  const health = useApi<SystemHealth>(
    () => api.get<SystemHealth>('/health/system').then((r) => r.data),
  );
  usePolling(() => health.reload(), 60_000);

  // The footer previously always read "System Operational" with a green pulse,
  // regardless of whether anything was actually up.
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
    <div className="flex items-center gap-1.5">
      <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
      {label}
    </div>
  );
}

export default function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 h-screen w-64 bg-slate-900/80 backdrop-blur-xl border-r border-slate-800 flex flex-col z-40">
      <div className="px-5 py-5 flex items-center gap-3 border-b border-slate-800">
        <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center font-bold text-white text-lg shadow-lg shadow-cyan-500/20">
          QX
        </div>
        <div>
          <h1 className="font-bold text-base leading-none tracking-tight text-white">QuantX</h1>
          <p className="text-[10px] text-slate-500 font-mono mt-0.5">TRADING PLATFORM</p>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                isActive
                  ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`
            }
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-4 py-3 border-t border-slate-800 text-xs text-slate-500">
        <SystemStatus />
      </div>
    </aside>
  );
}
