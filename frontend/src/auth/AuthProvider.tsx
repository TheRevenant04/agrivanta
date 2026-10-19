import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { sessionStore as defaultSessionStore } from '../services/sessionStore';
import type { SessionStore } from '../services/sessionStore';
import type { AuthSession } from '../services/types';
import { AuthContext, type AuthContextValue } from './authContext';

const SESSION_EXPIRED_MESSAGE =
  'Your session has expired. Please sign in again.';

export interface AuthProviderProps {
  children: ReactNode;
  /** Injectable store, used by tests; defaults to the browser store. */
  store?: SessionStore;
}

export function AuthProvider({
  children,
  store = defaultSessionStore,
}: AuthProviderProps) {
  const [session, setSession] = useState<AuthSession | null>(() => store.get());
  const [message, setMessage] = useState<string | null>(null);

  const signIn = useCallback(
    (next: AuthSession) => {
      store.save(next);
      setSession(next);
      setMessage(null);
    },
    [store],
  );

  const signOut = useCallback(() => {
    store.clear();
    setSession(null);
    setMessage(null);
  }, [store]);

  const handleUnauthorized = useCallback(() => {
    store.clear();
    setSession(null);
    setMessage(SESSION_EXPIRED_MESSAGE);
  }, [store]);

  const clearMessage = useCallback(() => setMessage(null), []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user: session?.user ?? null,
      token: session?.token ?? null,
      isAuthenticated: session !== null,
      message,
      signIn,
      signOut,
      handleUnauthorized,
      clearMessage,
    }),
    [session, message, signIn, signOut, handleUnauthorized, clearMessage],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
