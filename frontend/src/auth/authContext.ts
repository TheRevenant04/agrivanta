import { createContext, useContext } from 'react';
import type { AuthSession, User } from '../services/types';

export interface AuthContextValue {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  /** Redirect/expiry message shown on the login screen. */
  message: string | null;
  signIn(session: AuthSession): void;
  signOut(): void;
  /** Clears the session in response to a rejected/expired token. */
  handleUnauthorized(): void;
  clearMessage(): void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

/** Access auth state. Must be used within an AuthProvider. */
export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);

  if (!value) {
    throw new Error('useAuth must be used within an AuthProvider');
  }

  return value;
}
