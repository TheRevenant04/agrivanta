import { createHttpServices, type FetchLike } from './httpServices';
import { createMockServices } from './mockServices';
import { sessionStore as defaultSessionStore } from './sessionStore';
import type { SessionStore } from './sessionStore';
import type { AgrivantaServices } from '@/services/types';

export type ApiClientKind = 'mock' | 'http';

/** The environment variables the services layer reads. */
export interface ServicesEnv {
  VITE_API_CLIENT?: string;
  VITE_API_BASE_URL?: string;
}

/** Project Vite's env shape onto the two variables we care about. */
export function readServicesEnv(): ServicesEnv {
  return {
    VITE_API_CLIENT: import.meta.env.VITE_API_CLIENT,
    VITE_API_BASE_URL: import.meta.env.VITE_API_BASE_URL,
  };
}

export interface CreateServicesOptions {
  /** Overrides `VITE_API_CLIENT`; defaults to the resolved env value. */
  client?: ApiClientKind;
  /** Overrides `VITE_API_BASE_URL`. */
  baseUrl?: string;
  store?: SessionStore;
  fetchFn?: FetchLike;
  env?: ServicesEnv;
}

/**
 * `VITE_API_CLIENT` selects the implementation: anything other than `http`
 * (including unset) resolves to the mock, so the app runs with no backend.
 */
export function resolveApiClient(
  env: ServicesEnv = readServicesEnv(),
): ApiClientKind {
  return env.VITE_API_CLIENT?.trim().toLowerCase() === 'http' ? 'http' : 'mock';
}

/** `VITE_API_BASE_URL` is the base URL used by the HTTP implementation. */
export function resolveApiBaseUrl(
  env: ServicesEnv = readServicesEnv(),
): string {
  return env.VITE_API_BASE_URL?.trim() ?? '';
}

/**
 * Build the single services object the UI depends on.
 */
export function createServices(
  options: CreateServicesOptions = {},
): AgrivantaServices {
  const env = options.env ?? readServicesEnv();
  const client = options.client ?? resolveApiClient(env);
  const store = options.store ?? defaultSessionStore;

  if (client === 'http') {
    return createHttpServices({
      baseUrl: options.baseUrl ?? resolveApiBaseUrl(env),
      store,
      fetchFn: options.fetchFn,
    });
  }

  return createMockServices({ store });
}
