import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { AuthProvider } from './contexts/AuthContext';
import { useAuth } from './contexts/useAuth';
import DashboardLayout from './components/DashboardLayout';
import AgentPage from './pages/AgentPage';
import AnalyticsPage from './pages/AnalyticsPage';
import BacktestPage from './pages/BacktestPage';
import DashboardPage from './pages/DashboardPage';
import ExperimentsPage from './pages/ExperimentsPage';
import IndicatorsPage from './pages/IndicatorsPage';
import LiveTradingPage from './pages/LiveTradingPage';
import LoginPage from './pages/LoginPage';
import LogsPage from './pages/LogsPage';
import MarketDataPage from './pages/MarketDataPage';
import MarketMakingPage from './pages/MarketMakingPage';
import OrdersPage from './pages/OrdersPage';
import PaperTradingPage from './pages/PaperTradingPage';
import PositionsPage from './pages/PositionsPage';
import RiskPage from './pages/RiskPage';
import SettingsPage from './pages/SettingsPage';
import StrategiesPage from './pages/StrategiesPage';
import TradeJournalPage from './pages/TradeJournalPage';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400 font-mono text-sm">
        Loading QuantX Engine…
      </div>
    );
  }
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<ProtectedRoute><DashboardLayout /></ProtectedRoute>}>
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
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
