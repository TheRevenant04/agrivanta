import type { SessionStore } from './sessionStore';
import { sessionStore as defaultSessionStore } from './sessionStore';
import { createFarmSetupHttp } from './farmSetupHttp';
import { createInventoryHttp } from './inventoryHttp';
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
 * Extracts the backend's message (and offending field, when reported) from
 * an error response so forms can render it inline. Supports both a
 * `{ detail, field }` envelope and a field-keyed validation map such as
 * `{ name: ["This field is required."] }`.
 */
async function readErrorBody(
  response: Response,
): Promise<{ message?: string; field?: string }> {
  try {
    const payload: unknown = await response.json();

    if (typeof payload === 'object' && payload !== null) {
      const record = payload as Record<string, unknown>;

      if (typeof record.detail === 'string') {
        return {
          message: record.detail,
          field: typeof record.field === 'string' ? record.field : undefined,
        };
      }

      for (const [field, value] of Object.entries(record)) {
        if (Array.isArray(value) && typeof value[0] === 'string') {
          return { message: value[0], field };
        }
      }
    }
  } catch {
    // Non-JSON error bodies fall back to the generic message below.
  }

  return {};
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
      const detail = await readErrorBody(response);
      throw new ApiError(
        detail.message ??
          `Request to ${path} failed with status ${response.status}.`,
        response.status,
        detail.field,
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

    // Farm setup domains (issue #44) share the same auth/error plumbing.
    ...createFarmSetupHttp(request),

    // Inventory domain (issue #47) shares the same plumbing too.
    ...createInventoryHttp(request),
  };
}
