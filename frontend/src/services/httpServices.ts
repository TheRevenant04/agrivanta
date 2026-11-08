import type { SessionStore } from './sessionStore';
import { sessionStore as defaultSessionStore } from './sessionStore';
import { createFarmSetupHttp } from './farmSetupHttp';
import { createHarvestSaleHttp } from './harvestSaleHttp';
import { createExpensePaymentHttp } from './expensePaymentHttp';
import { createInventoryHttp } from './inventoryHttp';
import { createImportHttp } from './importHttp';
import { createActivityPlanningHttp } from './activityPlanningHttp';
// Crop cycle domain (issue #45).
import { createCropCycleHttp } from './cropCycleHttp';
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

  /**
   * Multipart upload helper (issue #24): posts a `FormData` body so the
   * browser sets the multipart content type, and reuses the same error
   * mapping as the JSON requests.
   */
  async function upload<T>(
    path: string,
    file: File,
    authenticated: boolean,
    fields: Record<string, string> = {},
  ): Promise<T> {
    const headers: Record<string, string> = {};

    if (authenticated) {
      const token = store.getToken();

      if (!token) {
        throw new UnauthorizedError();
      }

      headers.Authorization = `Bearer ${token}`;
    }

    const form = new FormData();
    form.append('file', file);
    for (const [name, value] of Object.entries(fields)) {
      form.append(name, value);
    }

    const response = await fetchFn(joinUrl(options.baseUrl, path), {
      method: 'POST',
      body: form,
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

    // Harvest and sale domains (issue #49) reuse the same auth/error plumbing.
    ...createHarvestSaleHttp(request),
    // Expense and payment domains (issue #49)
    ...createExpensePaymentHttp(request, upload),
    ...createImportHttp(request, upload),
    // Inventory domain (issue #47) shares the same plumbing too.
    ...createInventoryHttp(request),
    // Activity planning domains (issue #46) share the same plumbing.
    ...createActivityPlanningHttp(request),
    // Crop cycle domain (issue #45) shares the same auth/error plumbing.
    ...createCropCycleHttp(request),
  };
}
