import { useContext } from 'react';

import { AuthContext } from './auth-context';
import type { AuthContextType } from './auth-context';

/** Access the auth context; throws if used outside the provider. */
export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
