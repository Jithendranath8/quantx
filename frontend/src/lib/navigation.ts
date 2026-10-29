import {
  BookOpen, Bot, Cpu, FlaskConical, History, LayoutDashboard,
  Layers, LineChart, ListOrdered, PieChart, Scale, Settings, Shield, Terminal, TrendingUp, Wallet, Zap,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

/** Every in-app route lives under this prefix; `/` is the public home page. */
export const APP_BASE = '/app';

export interface NavPage {
  /** Path relative to APP_BASE ('' is the dashboard). */
  path: string;
  label: string;
  icon: LucideIcon;
  /** One line on what the page is for, shown in menus and the command palette. */
  summary: string;
}

export interface Workspace {
  id: string;
  label: string;
  /** What this group of pages answers, in the user's words. */
  question: string;
  pages: NavPage[];
}

// Five workspaces instead of one long sidebar: each answers a single question,
// so a newcomer only ever sees the handful of pages relevant to it.
export const WORKSPACES: Workspace[] = [
  {
    id: 'overview',
    label: 'Overview',
    question: 'How am I doing right now?',
    pages: [
      { path: '', label: 'Dashboard', icon: LayoutDashboard, summary: 'Portfolio value, allocation and platform health at a glance' },
    ],
  },
  {
    id: 'markets',
    label: 'Markets',
    question: 'What is the market doing?',
    pages: [
      { path: 'market', label: 'Market Data', icon: TrendingUp, summary: 'Live prices, order-book depth and stored candles' },
      { path: 'indicators', label: 'Indicators', icon: LineChart, summary: 'Multi-timeframe technical analysis for any symbol' },
    ],
  },
  {
    id: 'trading',
    label: 'Trading',
    question: 'What am I holding, and what may I risk?',
    pages: [
      { path: 'paper-trading', label: 'Paper Trading', icon: Wallet, summary: 'Simulated execution against live prices, with slippage and fees' },
      { path: 'positions', label: 'Positions', icon: Layers, summary: 'Open positions across your paper accounts' },
      { path: 'orders', label: 'Orders', icon: ListOrdered, summary: 'Paper order history for the selected account' },
      { path: 'strategies', label: 'Strategies', icon: Cpu, summary: 'Registered strategies and their live evaluation' },
      { path: 'risk', label: 'Risk Engine', icon: Shield, summary: 'Hard limits that AI signals cannot override' },
      { path: 'live', label: 'Live Trading', icon: Zap, summary: 'Real exchange execution behind two independent safety flags' },
    ],
  },
  {
    id: 'research',
    label: 'Research',
    question: 'Would this idea have worked?',
    pages: [
      { path: 'agent', label: 'AI Agent', icon: Bot, summary: 'Structured market context in, validated decision out' },
      { path: 'backtest', label: 'Backtesting', icon: History, summary: 'Event-driven simulation over stored candles' },
      { path: 'experiments', label: 'Research Suite', icon: FlaskConical, summary: 'Walk-forward, parameter search, Monte Carlo and causality audits' },
      { path: 'market-making', label: 'Market Making', icon: Scale, summary: 'Avellaneda–Stoikov inventory-aware quoting simulation' },
    ],
  },
  {
    id: 'insights',
    label: 'Insights',
    question: 'What did I learn?',
    pages: [
      { path: 'analytics', label: 'Analytics', icon: PieChart, summary: 'Portfolio performance and trade history export' },
      { path: 'journal', label: 'Trade Journal', icon: BookOpen, summary: 'Record setups, outcomes and lessons' },
      { path: 'logs', label: 'Event Ledger', icon: Terminal, summary: 'Immutable audit trail of everything done on your behalf' },
      { path: 'settings', label: 'Settings', icon: Settings, summary: 'Your account and platform configuration' },
    ],
  },
];

export function appPath(path: string): string {
  return path ? `${APP_BASE}/${path}` : APP_BASE;
}

/** The workspace owning a pathname, defaulting to Overview. */
export function workspaceFor(pathname: string): Workspace {
  const rest = pathname.startsWith(APP_BASE) ? pathname.slice(APP_BASE.length).replace(/^\//, '') : '';
  const first = rest.split('/')[0];
  return WORKSPACES.find((w) => w.pages.some((p) => p.path === first)) ?? WORKSPACES[0];
}

export const ALL_PAGES = WORKSPACES.flatMap((w) => w.pages.map((p) => ({ ...p, workspace: w.label })));
