import type { SessionStore } from './sessionStore';
import { sessionStore as defaultSessionStore } from './sessionStore';
import {
  ApiError,
  InvalidCredentialsError,
  UnauthorizedError,
  type AgrivantaServices,
  type AuthSession,
  type LoginCredentials,
  type RegisterInput,
  type User,
} from './types';

export type FetchLike = (
  input: string,
  init?: RequestInit,
) => Promise<Response>;

export interface HttpServicesOptions {
  /** Base URL prepended to every request path, e.g. `http://localhost:8000/api`. */
  baseUrl: string;
  store?: SessionStore;
  /** Injectable fetch, primarily for tests. */
  fetchFn?: FetchLike;
}

function joinUrl(baseUrl: string, path: string): string {
  return `${baseUrl.replace(/\/+$/, '')}${path}`;
}

/**
 * Real HTTP implementation of {@link AgrivantaServices}. It is a thin fetch
 * wrapper and never touches the DOM beyond storing the session.
 */
export function createHttpServices(
  options: HttpServicesOptions,
): AgrivantaServices {
  const store = options.store ?? defaultSessionStore;
  const fetchFn = options.fetchFn ?? globalThis.fetch.bind(globalThis);

  async function request<T>(
    path: string,
    init: RequestInit,
    authenticated: boolean,
  ): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(init.headers as Record<string, string> | undefined),
    };

    if (authenticated) {
      const token = store.getToken();

      if (!token) {
        throw new UnauthorizedError();
      }

      headers.Authorization = `Bearer ${token}`;
    }

    const response = await fetchFn(joinUrl(options.baseUrl, path), {
      ...init,
      headers,
    });

    if (response.status === 401) {
      throw authenticated
        ? new UnauthorizedError()
        : new InvalidCredentialsError();
    }

    if (!response.ok) {
      throw new ApiError(
        `Request to ${path} failed with status ${response.status}.`,
        response.status,
      );
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  }

  async function persistSession(session: AuthSession): Promise<AuthSession> {
    store.save(session);
    return session;
  }

  return {
    auth: {
      login(credentials: LoginCredentials) {
        return request<AuthSession>(
          '/auth/login',
          { method: 'POST', body: JSON.stringify(credentials) },
          false,
        ).then(persistSession);
      },

      register(input: RegisterInput) {
        return request<AuthSession>(
          '/auth/register',
          { method: 'POST', body: JSON.stringify(input) },
          false,
        ).then(persistSession);
      },

      async logout() {
        try {
          await request<void>('/auth/logout', { method: 'POST' }, true);
        } finally {
          store.clear();
        }
      },

      me() {
        return request<User>('/auth/me', { method: 'GET' }, true);
      },
    },
  };
}
