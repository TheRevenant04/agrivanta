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

  const guardDomain = <D,>(domain: D): D => {
    const guarded = Object.fromEntries(
      Object.entries(domain as Record<string, unknown>).map(([key, value]) => [
        key,
        typeof value === 'function'
          ? guard(value as (...args: never[]) => Promise<never>, onUnauthorized)
          : value,
      ]),
    );
    return guarded as unknown as D;
  };

  return {
    ...services,
    auth,
    farm: guardDomain(services.farm),
    fields: guardDomain(services.fields),
    crops: guardDomain(services.crops),
    varieties: guardDomain(services.varieties),
    units: guardDomain(services.units),
    conversions: guardDomain(services.conversions),
    // Harvest and sale domains (issue #49) get the same 401 handling.
    harvests: guardDomain(services.harvests),
    sales: guardDomain(services.sales),
    // Expense and payment domains (issue #49) need the same 401 guard.
    expenses: guardDomain(services.expenses),
    payments: guardDomain(services.payments),
    imports: guardDomain(services.imports),
    reporting: guardDomain(services.reporting),
    // Inventory domain (issue #47).
    items: guardDomain(services.items),
    movements: guardDomain(services.movements),
    // Activity planning domains (issue #46).
    activities: guardDomain(services.activities),
    activityTypes: guardDomain(services.activityTypes),
    // Crop cycle domain (issue #45).
    cropCycles: guardDomain(services.cropCycles),
  };
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
