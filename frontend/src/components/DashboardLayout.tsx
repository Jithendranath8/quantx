import { LogOut } from 'lucide-react';
import { Outlet } from 'react-router-dom';

import Sidebar from './Sidebar';
import { useAuth } from '../contexts/useAuth';

export default function DashboardLayout() {
  const { user, logout } = useAuth();
  const initial = (user?.email?.[0] ?? 'Q').toUpperCase();

  return (
    <div className="min-h-screen">
      <Sidebar />

      <div className="ml-64">
        <header className="sticky top-0 z-30 h-14 bg-slate-950/60 backdrop-blur-xl border-b hairline flex items-center justify-end px-6">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2.5 rounded-full py-1 pl-1 pr-3 ring-1 ring-inset ring-white/[0.07] bg-white/[0.02]">
              <span className="grid place-items-center w-6 h-6 rounded-full bg-brand-gradient text-[11px] font-bold text-white">
                {initial}
              </span>
              <span className="text-xs text-slate-300 font-mono max-w-[200px] truncate">{user?.email}</span>
            </div>
            <button
              type="button"
              onClick={() => void logout()}
              className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-red-400 transition-colors"
            >
              <LogOut className="w-3.5 h-3.5" />
              Logout
            </button>
          </div>
        </header>

        <main className="p-6">
          <div className="mx-auto max-w-[1600px] animate-fade-in">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
