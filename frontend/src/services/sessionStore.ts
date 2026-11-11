import type { AuthSession } from '@/services/types';

/** localStorage key under which the authenticated session is persisted. */
export const SESSION_STORAGE_KEY = 'agrivanta.session';

export interface SessionStore {
  get(): AuthSession | null;
  getToken(): string | null;
  save(session: AuthSession): void;
  clear(): void;
}

type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function parseSession(raw: string | null): AuthSession | null {
  if (!raw) {
    return null;
  }

  try {
    const parsed: unknown = JSON.parse(raw);

    if (
      typeof parsed === 'object' &&
      parsed !== null &&
      typeof (parsed as { token?: unknown }).token === 'string' &&
      typeof (parsed as { user?: unknown }).user === 'object' &&
      (parsed as { user?: unknown }).user !== null
    ) {
      return parsed as AuthSession;
    }
  } catch {
    // Malformed payloads are treated as "no session" rather than crashing.
  }

  return null;
}

/**
 * Persist the session in a Web Storage object so it survives a page refresh.
 */
export function createSessionStore(
  storage: StorageLike = window.localStorage,
): SessionStore {
  return {
    get: () => parseSession(storage.getItem(SESSION_STORAGE_KEY)),
    getToken: () =>
      parseSession(storage.getItem(SESSION_STORAGE_KEY))?.token ?? null,
    save: (session) =>
      storage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session)),
    clear: () => storage.removeItem(SESSION_STORAGE_KEY),
  };
}

/** In-memory session store, used by tests and non-browser environments. */
export function createMemorySessionStore(): SessionStore {
  let raw: string | null = null;

  return {
    get: () => parseSession(raw),
    getToken: () => parseSession(raw)?.token ?? null,
    save: (session) => {
      raw = JSON.stringify(session);
    },
    clear: () => {
      raw = null;
    },
  };
}

/** Shared browser session store. */
export const sessionStore = createSessionStore();
