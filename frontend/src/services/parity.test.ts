import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createServices, resolveApiClient } from './createServices';
import { createHttpServices } from './httpServices';
import { createMockServices } from './mockServices';
import { createMemorySessionStore, type SessionStore } from './sessionStore';
import type { AgrivantaServices, AuthSession, User } from './types';

const BASE_URL = 'https://api.agrivanta.test/v1';
const VALID = { email: 'owner@agrivanta.test', password: 'password123' };

interface RecordedRequest {
  url: string;
  init: RequestInit | undefined;
}

interface FakeBackend {
  fetchFn: (input: string, init?: RequestInit) => Promise<Response>;
  requests: RecordedRequest[];
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function readTokenHeader(init: RequestInit | undefined): string | null {
  const headers = init?.headers as Record<string, string> | undefined;
  const header = headers?.Authorization;
  return header ? header.replace(/^Bearer\s+/, '') : null;
}

/**
 * Minimal in-memory stand-in for the backend so the HTTP implementation can
 * be exercised with the same expectations as the mock.
 */
function createFakeBackend(): FakeBackend {
  const users = new Map<string, { password: string; user: User }>();
  users.set(VALID.email, {
    password: VALID.password,
    user: { id: 'user-owner', email: VALID.email, role: 'owner' },
  });
  const sessions = new Map<string, User>();
  const requests: RecordedRequest[] = [];
  let sequence = 1;

  async function fetchFn(
    input: string,
    init: RequestInit = {},
  ): Promise<Response> {
    requests.push({ url: input, init });

    const path = new URL(input).pathname;
    const method = init.method ?? 'GET';

    if (method === 'POST' && path.endsWith('/auth/login')) {
      const body = JSON.parse(String(init.body)) as {
        email: string;
        password: string;
      };
      const record = users.get(body.email);

      if (!record || record.password !== body.password) {
        return json({ detail: 'Invalid credentials' }, 401);
      }

      const token = `token-${record.user.id}`;
      sessions.set(token, record.user);
      return json({ token, user: record.user });
    }

    if (method === 'POST' && path.endsWith('/auth/register')) {
      const body = JSON.parse(String(init.body)) as {
        email: string;
        password: string;
      };

      if (users.has(body.email)) {
        return json({ detail: 'Already registered' }, 409);
      }

      sequence += 1;
      const user: User = {
        id: `user-${sequence}`,
        email: body.email,
        role: 'owner',
      };
      users.set(body.email, { password: body.password, user });

      const token = `token-${user.id}`;
      sessions.set(token, user);
      return json({ token, user }, 201);
    }

    if (method === 'GET' && path.endsWith('/auth/me')) {
      const token = readTokenHeader(init);
      const user = token ? sessions.get(token) : undefined;

      if (!user) {
        return json({ detail: 'Unauthorized' }, 401);
      }

      return json(user);
    }

    if (method === 'POST' && path.endsWith('/auth/logout')) {
      const token = readTokenHeader(init);
      if (token) {
        sessions.delete(token);
      }
      return new Response(null, { status: 204 });
    }

    return json({ detail: 'Not found' }, 404);
  }

  return { fetchFn, requests };
}

interface Harness {
  services: AgrivantaServices;
  store: SessionStore;
  requests: RecordedRequest[];
}

type MakeHarness = () => Harness;

const implementations: Array<[string, MakeHarness]> = [
  [
    'mock',
    () => {
      const store = createMemorySessionStore();
      return { services: createMockServices({ store }), store, requests: [] };
    },
  ],
  [
    'http',
    () => {
      const store = createMemorySessionStore();
      const backend = createFakeBackend();
      return {
        services: createHttpServices({
          baseUrl: BASE_URL,
          store,
          fetchFn: backend.fetchFn,
        }),
        store,
        requests: backend.requests,
      };
    },
  ],
];

describe.each(implementations)(
  '%s implementation conformance',
  (_name, make) => {
    let harness: Harness;

    beforeEach(() => {
      harness = make();
    });

    it('login resolves the typed session shape and persists the token', async () => {
      const session: AuthSession = await harness.services.auth.login(VALID);

      expect(session).toEqual({
        token: expect.any(String),
        user: {
          id: expect.any(String),
          email: VALID.email,
          role: expect.any(String),
        },
      });
      expect(harness.store.getToken()).toBe(session.token);
    });

    it('login rejects invalid credentials and persists no token', async () => {
      await expect(
        harness.services.auth.login({ email: VALID.email, password: 'nope' }),
      ).rejects.toMatchObject({ status: 401 });
      expect(harness.store.getToken()).toBeNull();
    });

    it('me() returns the authenticated user', async () => {
      const session = await harness.services.auth.login(VALID);
      await expect(harness.services.auth.me()).resolves.toEqual(session.user);
    });

    it('me() rejects with 401 when no token is stored', async () => {
      await expect(harness.services.auth.me()).rejects.toMatchObject({
        status: 401,
      });
    });

    it('logout clears the token and me() rejects afterwards', async () => {
      await harness.services.auth.login(VALID);
      await harness.services.auth.logout();

      expect(harness.store.getToken()).toBeNull();
      await expect(harness.services.auth.me()).rejects.toMatchObject({
        status: 401,
      });
    });

    it('register creates an account, persists the session, and allows login', async () => {
      const input = {
        name: 'New Farmer',
        email: 'new@agrivanta.test',
        password: 'secret123',
      };

      const session = await harness.services.auth.register(input);

      expect(session.user).toEqual({
        id: expect.any(String),
        email: input.email,
        role: expect.any(String),
      });
      expect(harness.store.getToken()).toBe(session.token);

      await expect(
        harness.services.auth.login({
          email: input.email,
          password: input.password,
        }),
      ).resolves.toMatchObject({ user: { email: input.email } });
    });

    it('register rejects a duplicate email', async () => {
      await expect(
        harness.services.auth.register({
          email: VALID.email,
          password: 'again',
        }),
      ).rejects.toMatchObject({ status: 409 });
    });
  },
);

describe('API client selection and base URL', () => {
  it('defaults to mock when VITE_API_CLIENT is unset or unknown', () => {
    expect(resolveApiClient({})).toBe('mock');
    expect(resolveApiClient({ VITE_API_CLIENT: 'mock' })).toBe('mock');
    expect(resolveApiClient({ VITE_API_CLIENT: 'something-else' })).toBe(
      'mock',
    );
    expect(resolveApiClient({ VITE_API_CLIENT: ' HTTP ' })).toBe('http');
  });

  it('createServices selects http from VITE_API_CLIENT and uses VITE_API_BASE_URL', async () => {
    const backend = createFakeBackend();
    const store = createMemorySessionStore();
    const services = createServices({
      env: { VITE_API_CLIENT: 'http', VITE_API_BASE_URL: BASE_URL },
      store,
      fetchFn: backend.fetchFn,
    });

    const session = await services.auth.login(VALID);
    expect(backend.requests[0]?.url).toBe(`${BASE_URL}/auth/login`);

    await services.auth.me();
    const meRequest = backend.requests.find((request) =>
      request.url.endsWith('/auth/me'),
    );
    expect(meRequest?.init?.headers).toMatchObject({
      Authorization: `Bearer ${session.token}`,
    });
  });

  it('normalises a trailing slash on the base URL', async () => {
    const backend = createFakeBackend();
    const services = createHttpServices({
      baseUrl: `${BASE_URL}/`,
      store: createMemorySessionStore(),
      fetchFn: backend.fetchFn,
    });

    await services.auth.login(VALID);
    expect(backend.requests[0]?.url).toBe(`${BASE_URL}/auth/login`);
  });

  it('createServices defaults to the mock when the env is empty', async () => {
    const fetchSpy = vi.fn(() =>
      Promise.reject(new Error('fetch must not be called for mock')),
    );
    const services = createServices({
      env: {},
      store: createMemorySessionStore(),
      fetchFn: fetchSpy,
    });

    await expect(services.auth.login(VALID)).resolves.toMatchObject({
      user: { email: VALID.email },
    });
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
