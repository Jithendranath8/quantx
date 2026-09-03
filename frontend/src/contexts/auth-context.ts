import { createContext } from 'react';

import type { User } from '../lib/types';

export interface AuthContextType {
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, username: string, password: string, fullName?: string) => Promise<void>;
  logout: () => Promise<void>;
  isAuthenticated: boolean;
  isLoading: boolean;
}

/**
 * The context object itself, separate from the provider component.
 *
 * Vite's fast refresh only preserves state for modules that export components
 * exclusively, so the context and the hook live outside AuthContext.tsx.
 */
export const AuthContext = createContext<AuthContextType | null>(null);
