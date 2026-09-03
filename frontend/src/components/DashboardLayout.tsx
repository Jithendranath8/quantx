import { Outlet } from 'react-router-dom';

import Sidebar from './Sidebar';
import { useAuth } from '../contexts/useAuth';

export default function DashboardLayout() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-slate-950">
      <Sidebar />

      <div className="ml-64">
        <header className="sticky top-0 z-30 h-14 bg-slate-900/60 backdrop-blur-lg border-b border-slate-800 flex items-center justify-between px-6">
          <div />
          <div className="flex items-center gap-4">
            <span className="text-xs text-slate-400 font-mono">{user?.email}</span>
            <button
              type="button"
              onClick={() => void logout()}
              className="text-xs text-slate-500 hover:text-red-400 transition-colors"
            >
              Logout
            </button>
          </div>
        </header>

        <main className="p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
