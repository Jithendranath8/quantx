import React, { lazy } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { AuthProvider } from './contexts/AuthContext';
import { useAuth } from './contexts/useAuth';
import AppShell from './components/shell/AppShell';
import { LogoMark } from './components/brand/Logo';
import { ALL_PAGES, APP_BASE } from './lib/navigation';
import AuthCallbackPage from './pages/AuthCallbackPage';
import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';

// App pages load on demand, so the public home and login pages stay light.
const AgentPage = lazy(() => import('./pages/AgentPage'));
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'));
const BacktestPage = lazy(() => import('./pages/BacktestPage'));
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const ExperimentsPage = lazy(() => import('./pages/ExperimentsPage'));
const IndicatorsPage = lazy(() => import('./pages/IndicatorsPage'));
const LiveTradingPage = lazy(() => import('./pages/LiveTradingPage'));
const LogsPage = lazy(() => import('./pages/LogsPage'));
const MarketDataPage = lazy(() => import('./pages/MarketDataPage'));
const MarketMakingPage = lazy(() => import('./pages/MarketMakingPage'));
const OrdersPage = lazy(() => import('./pages/OrdersPage'));
const PaperTradingPage = lazy(() => import('./pages/PaperTradingPage'));
const PositionsPage = lazy(() => import('./pages/PositionsPage'));
const RiskPage = lazy(() => import('./pages/RiskPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const StrategiesPage = lazy(() => import('./pages/StrategiesPage'));
const TradeJournalPage = lazy(() => import('./pages/TradeJournalPage'));

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 text-zinc-500 text-sm">
        <LogoMark className="w-10 h-10 animate-pulse" />
        Loading QuantX…
      </div>
    );
  }
  return isAuthenticated ? (
    <>{children}</>
  ) : (
    <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />
  );
}

/** Pages moved under /app; old bookmarks land on the same page, not the home page. */
function LegacyRedirect() {
  const { pathname, search } = useLocation();
  const first = pathname.replace(/^\//, '').split('/')[0];
  const known = ALL_PAGES.some((p) => p.path && p.path === first);
  return <Navigate to={known ? `${APP_BASE}${pathname}${search}` : '/'} replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/auth/callback" element={<AuthCallbackPage />} />
          <Route path={APP_BASE} element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
            <Route index element={<DashboardPage />} />
            <Route path="market" element={<MarketDataPage />} />
            <Route path="positions" element={<PositionsPage />} />
            <Route path="orders" element={<OrdersPage />} />
            <Route path="indicators" element={<IndicatorsPage />} />
            <Route path="strategies" element={<StrategiesPage />} />
            <Route path="agent" element={<AgentPage />} />
            <Route path="risk" element={<RiskPage />} />
            <Route path="paper-trading" element={<PaperTradingPage />} />
            <Route path="backtest" element={<BacktestPage />} />
            <Route path="market-making" element={<MarketMakingPage />} />
            <Route path="experiments" element={<ExperimentsPage />} />
            <Route path="journal" element={<TradeJournalPage />} />
            <Route path="live" element={<LiveTradingPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="logs" element={<LogsPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
          <Route path="*" element={<LegacyRedirect />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
