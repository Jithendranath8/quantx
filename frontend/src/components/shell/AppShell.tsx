import { Suspense, useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { BookOpenText, ChevronDown, Home, LogOut, Menu, Search, Settings, X } from 'lucide-react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';

import CommandPalette from './CommandPalette';
import { LoadingState } from '../ui';
import { Logo } from '../brand/Logo';
import { useAuth } from '../../contexts/useAuth';
import api from '../../lib/api';
import { APP_BASE, WORKSPACES, appPath, workspaceFor } from '../../lib/navigation';
import { recordVisit } from '../../lib/onboarding';
import { useApi, usePolling } from '../../lib/useApi';
import type { SystemHealth } from '../../lib/types';

/** Header status pill, driven by the real health endpoint. */
function SystemStatus() {
  const health = useApi<SystemHealth>(() => api.get<SystemHealth>('/health/system').then((r) => r.data));
  usePolling(() => health.reload(), 60_000);

  const { label, dot } = health.error
    ? { label: 'Status unavailable', dot: 'bg-zinc-500' }
    : health.data?.status === 'HEALTHY'
      ? { label: 'Operational', dot: 'bg-emerald-400' }
      : health.data?.status === 'DEGRADED'
        ? { label: 'Degraded', dot: 'bg-yellow-400' }
        : health.data
          ? { label: 'Unhealthy', dot: 'bg-red-400' }
          : { label: 'Checking', dot: 'bg-zinc-600' };

  return (
    <Link
      to={appPath('')}
      title="System health — details on the dashboard"
      className="hidden md:inline-flex items-center gap-2 h-8 rounded-full px-3 text-xs text-zinc-300 ring-1 ring-inset ring-white/[0.08] hover:ring-white/20 transition cursor-pointer"
    >
      <span className="relative flex h-2 w-2">
        <span className={`absolute inline-flex h-full w-full rounded-full ${dot} opacity-60 animate-ping`} />
        <span className={`relative inline-flex h-2 w-2 rounded-full ${dot}`} />
      </span>
      {label}
    </Link>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const initial = (user?.email?.[0] ?? 'Q').toUpperCase();

  return (
    <div className="d-dropdown d-dropdown-end">
      <div
        tabIndex={0}
        role="button"
        className="flex items-center gap-2 h-8 rounded-full pl-1 pr-2 ring-1 ring-inset ring-white/[0.08] hover:ring-white/20 transition cursor-pointer"
      >
        <span className="grid place-items-center w-6 h-6 rounded-full bg-brand-gradient text-[11px] font-bold text-black">
          {initial}
        </span>
        <ChevronDown className="w-3.5 h-3.5 text-zinc-500" />
      </div>
      <ul
        tabIndex={0}
        className="d-dropdown-content z-50 mt-2 w-64 rounded-2xl border border-white/10 bg-ink-900/95 p-2 shadow-2xl backdrop-blur-xl"
      >
        <li className="px-3 py-2.5 border-b border-white/[0.06] mb-1">
          <p className="text-[11px] uppercase tracking-wider text-zinc-500">Signed in as</p>
          <p className="text-sm text-white truncate">{user?.email}</p>
        </li>
        <li>
          <Link to={appPath('settings')} className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-zinc-300 hover:bg-white/[0.05] hover:text-white">
            <Settings className="w-4 h-4" /> Settings
          </Link>
        </li>
        <li>
          <Link to="/#how-it-works" className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-zinc-300 hover:bg-white/[0.05] hover:text-white">
            <BookOpenText className="w-4 h-4" /> How QuantX works
          </Link>
        </li>
        <li>
          <Link to="/" className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-zinc-300 hover:bg-white/[0.05] hover:text-white">
            <Home className="w-4 h-4" /> Home page
          </Link>
        </li>
        <li>
          <button
            type="button"
            onClick={() => void logout()}
            className="w-full flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-zinc-300 hover:bg-red-500/10 hover:text-red-300 cursor-pointer"
          >
            <LogOut className="w-4 h-4" /> Sign out
          </button>
        </li>
      </ul>
    </div>
  );
}

/** Mobile navigation: every workspace and page in one sheet. */
function MobileNav({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[55] lg:hidden">
      <button type="button" aria-label="Close menu" className="absolute inset-0 bg-black/60" onClick={onClose} />
      <motion.nav
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        transition={{ type: 'spring', stiffness: 380, damping: 36 }}
        className="absolute right-0 top-0 h-full w-[min(20rem,86vw)] overflow-y-auto border-l border-white/10 bg-ink-900 p-4"
        aria-label="Main"
      >
        <div className="flex items-center justify-between mb-4">
          <Logo to={appPath('')} />
          <button type="button" onClick={onClose} aria-label="Close menu" className="p-2 text-zinc-400 hover:text-white cursor-pointer">
            <X className="w-5 h-5" />
          </button>
        </div>
        {WORKSPACES.map((w) => (
          <div key={w.id} className="mb-4">
            <p className="px-2 mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-zinc-500">{w.label}</p>
            {w.pages.map((p) => (
              <NavLink
                key={p.path}
                to={appPath(p.path)}
                end={p.path === ''}
                onClick={onClose}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-lg px-2 py-2 text-sm ${
                    isActive ? 'bg-white/[0.06] text-white' : 'text-zinc-400 hover:text-white'
                  }`
                }
              >
                <p.icon className="w-4 h-4" />
                {p.label}
              </NavLink>
            ))}
          </div>
        ))}
      </motion.nav>
    </div>
  );
}

export default function AppShell() {
  const { pathname } = useLocation();
  const current = workspaceFor(pathname);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
    window.scrollTo({ top: 0 });
    recordVisit(pathname.slice(APP_BASE.length).replace(/^\//, '').split('/')[0]);
  }, [pathname]);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-ink-950/75 backdrop-blur-xl">
        {/* Primary row: brand, workspaces, global actions. */}
        <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-6 px-4 sm:px-6">
          <Logo to={appPath('')} />

          <nav className="hidden lg:flex items-center gap-1" aria-label="Workspaces">
            {WORKSPACES.map((w) => {
              const isActive = w.id === current.id;
              return (
                <Link
                  key={w.id}
                  to={appPath(w.pages[0].path)}
                  className={`relative rounded-full px-3.5 py-1.5 text-sm transition-colors cursor-pointer ${
                    isActive ? 'text-white' : 'text-zinc-400 hover:text-zinc-100'
                  }`}
                >
                  {isActive && (
                    <motion.span
                      layoutId="workspace-pill"
                      className="absolute inset-0 rounded-full bg-white/[0.07] ring-1 ring-inset ring-white/10"
                      transition={{ type: 'spring', stiffness: 500, damping: 38 }}
                    />
                  )}
                  <span className="relative">{w.label}</span>
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              className="hidden sm:flex items-center gap-2 h-8 w-56 rounded-full px-3 text-xs text-zinc-500 ring-1 ring-inset ring-white/[0.08] hover:ring-white/20 hover:text-zinc-300 transition cursor-pointer"
            >
              <Search className="w-3.5 h-3.5" />
              Jump to a page…
              <kbd className="ml-auto font-mono text-[10px] text-zinc-500">⌘K</kbd>
            </button>
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              aria-label="Search pages"
              className="sm:hidden p-2 text-zinc-400 hover:text-white cursor-pointer"
            >
              <Search className="w-4 h-4" />
            </button>
            <SystemStatus />
            <UserMenu />
            <button
              type="button"
              onClick={() => setMobileOpen(true)}
              aria-label="Open menu"
              className="lg:hidden p-2 text-zinc-400 hover:text-white cursor-pointer"
            >
              <Menu className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Secondary row: only the pages of the current workspace. */}
        <div className="border-t border-white/[0.04]">
          <div className="mx-auto flex h-11 max-w-[1600px] items-center gap-5 px-4 sm:px-6 overflow-x-auto">
            <span className="hidden md:block shrink-0 text-xs text-zinc-500 font-display italic text-[15px]">
              {current.question}
            </span>
            <span className="hidden md:block h-4 w-px bg-white/10 shrink-0" />
            <nav className="flex items-center gap-1" aria-label={`${current.label} pages`}>
              {current.pages.map((p) => (
                <NavLink
                  key={p.path}
                  to={appPath(p.path)}
                  end={p.path === ''}
                  title={p.summary}
                  className={({ isActive }) =>
                    `relative flex items-center gap-2 shrink-0 rounded-md px-2.5 py-1.5 text-[13px] transition-colors cursor-pointer ${
                      isActive ? 'text-white' : 'text-zinc-400 hover:text-zinc-100'
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      <p.icon className={`w-3.5 h-3.5 ${isActive ? 'text-brand-400' : ''}`} />
                      {p.label}
                      {isActive && (
                        <motion.span
                          layoutId="page-underline"
                          className="absolute -bottom-[7px] left-2 right-2 h-[2px] rounded-full bg-brand-500"
                          transition={{ type: 'spring', stiffness: 500, damping: 38 }}
                        />
                      )}
                    </>
                  )}
                </NavLink>
              ))}
            </nav>
          </div>
        </div>
      </header>

      <main className="px-4 sm:px-6 py-8">
        <div key={pathname} className="mx-auto max-w-[1600px] animate-fade-in-up">
          <Suspense fallback={<LoadingState />}>
            <Outlet />
          </Suspense>
        </div>
      </main>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      <MobileNav open={mobileOpen} onClose={() => setMobileOpen(false)} />
    </div>
  );
}
