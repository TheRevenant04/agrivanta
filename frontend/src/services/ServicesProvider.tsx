import { useMemo, type ReactNode } from 'react';
import { createServices } from './createServices';
import { ServicesContext } from './servicesContext';
import {
  isUnauthorizedError,
  type AgrivantaServices,
  type AuthService,
} from './types';

function noop() {
  // Default when no unauthorized handler is wired in (e.g. isolated tests).
}

function guard<Args extends unknown[], Result>(
  fn: (...args: Args) => Promise<Result>,
  onUnauthorized: () => void,
): (...args: Args) => Promise<Result> {
  return async (...args) => {
    try {
      return await fn(...args);
    } catch (error) {
      if (isUnauthorizedError(error)) {
        onUnauthorized();
      }
      throw error;
    }
  };
}

/**
 * Route the authenticated auth methods through a 401 guard so a
 * rejected/expired token can clear the stored session.
 */
function withUnauthorizedHandling(
  services: AgrivantaServices,
  onUnauthorized: () => void,
): AgrivantaServices {
  const auth: AuthService = {
    login: (credentials) => services.auth.login(credentials),
    register: (input) => services.auth.register(input),
    logout: guard(() => services.auth.logout(), onUnauthorized),
    me: guard(() => services.auth.me(), onUnauthorized),
  };

  return { ...services, auth };
}

export interface ServicesProviderProps {
  children: ReactNode;
  /** Injectable services, used by tests; defaults to the env-selected client. */
  services?: AgrivantaServices;
  /**
   * Called when an authenticated request is rejected (401). The app wires this
   * to the auth layer so the session is cleared and the visitor is redirected.
   */
  onUnauthorized?: () => void;
}

export function ServicesProvider({
  children,
  services,
  onUnauthorized = noop,
}: ServicesProviderProps) {
  const value = useMemo(
    () =>
      withUnauthorizedHandling(services ?? createServices(), onUnauthorized),
    [services, onUnauthorized],
  );

  return (
    <ServicesContext.Provider value={value}>
      {children}
    </ServicesContext.Provider>
  );
}
