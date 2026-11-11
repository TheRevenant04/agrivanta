import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createServices, resolveApiClient } from '@/services/createServices';
import { createFarmSetupMock, type FarmSetupSeed } from '@/services/farmSetupMock';
import { createHttpServices } from '@/services/httpServices';
import { createMockServices } from '@/services/mockServices';
import { createMemorySessionStore, type SessionStore } from '@/services/sessionStore';
import {
  isApiError,
  type AgrivantaServices,
  type AuthSession,
  type ConversionInput,
  type ConversionQuery,
  type CropInput,
  type FarmInput,
  type FieldInput,
  type UnitInput,
  type User,
  type VarietyInput,
} from '@/services/types';

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
 * be exercised with the same expectations as the mock. The farm setup
 * endpoints delegate to the shared mock engine (with auth enforced here at
 * the HTTP boundary) so both implementations are held to one rule set.
 */
function createFakeBackend(seed?: FarmSetupSeed): FakeBackend {
  const users = new Map<string, { password: string; user: User }>();
  users.set(VALID.email, {
    password: VALID.password,
    user: { id: 'user-owner', email: VALID.email, role: 'owner' },
  });
  const sessions = new Map<string, User>();
  const requests: RecordedRequest[] = [];
  const setup = createFarmSetupMock({
    seed,
    requireAuth: () => undefined,
  });
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

    // Farm setup endpoints: same routes the HTTP implementation calls.
    const setupMatch =
      /\/(farm|fields|crops|varieties|units|conversions)(\/[^/]+)?$/.exec(path);

    if (setupMatch) {
      const resource = setupMatch[1];
      const rest = setupMatch[2] ?? '';
      const token = readTokenHeader(init);

      if (!token || !sessions.has(token)) {
        return json({ detail: 'Unauthorized' }, 401);
      }

      const payload: unknown = init.body ? JSON.parse(String(init.body)) : {};

      try {
        switch (resource) {
          case 'farm':
            if (method === 'GET') {
              return json(await setup.farm.get());
            }
            if (method === 'PUT') {
              return json(await setup.farm.update(payload as FarmInput));
            }
            break;
          case 'fields':
            if (method === 'GET') {
              return json(await setup.fields.list());
            }
            if (method === 'POST') {
              return json(
                await setup.fields.create(payload as FieldInput),
                201,
              );
            }
            if (method === 'PUT') {
              return json(
                await setup.fields.update(rest.slice(1), payload as FieldInput),
              );
            }
            break;
          case 'crops':
            if (method === 'GET') {
              return json(await setup.crops.list());
            }
            if (method === 'POST') {
              return json(await setup.crops.create(payload as CropInput), 201);
            }
            if (method === 'PUT') {
              return json(
                await setup.crops.update(rest.slice(1), payload as CropInput),
              );
            }
            break;
          case 'varieties':
            if (method === 'GET') {
              const crop = new URL(input).searchParams.get('crop');
              return json(await setup.varieties.list(crop ?? undefined));
            }
            if (method === 'POST') {
              return json(
                await setup.varieties.create(payload as VarietyInput),
                201,
              );
            }
            if (method === 'PUT') {
              return json(
                await setup.varieties.update(
                  rest.slice(1),
                  payload as VarietyInput,
                ),
              );
            }
            break;
          case 'units':
            if (method === 'GET') {
              return json(await setup.units.list());
            }
            if (method === 'POST') {
              return json(await setup.units.create(payload as UnitInput), 201);
            }
            if (method === 'PUT') {
              return json(
                await setup.units.update(rest.slice(1), payload as UnitInput),
              );
            }
            break;
          case 'conversions':
            if (rest === '/convert' && method === 'POST') {
              return json(
                await setup.conversions.convert(payload as ConversionQuery),
              );
            }
            if (method === 'GET') {
              return json(await setup.conversions.list());
            }
            if (method === 'POST') {
              return json(
                await setup.conversions.create(payload as ConversionInput),
                201,
              );
            }
            break;
        }

        return json({ detail: 'Not found' }, 404);
      } catch (error) {
        if (isApiError(error)) {
          return json(
            { detail: error.message, field: error.field },
            error.status,
          );
        }
        throw error;
      }
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

type MakeHarness = (seed?: FarmSetupSeed) => Harness;

const implementations: Array<[string, MakeHarness]> = [
  [
    'mock',
    (seed) => {
      const store = createMemorySessionStore();
      return {
        services: createMockServices({ store, farmSetup: seed }),
        store,
        requests: [],
      };
    },
  ],
  [
    'http',
    (seed) => {
      const store = createMemorySessionStore();
      const backend = createFakeBackend(seed);
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

const FARM_SETUP_SEED: FarmSetupSeed = {
  farm: { id: 'farm-1', name: 'Willow Creek Farm', reportingCurrency: 'USD' },
  fields: [],
  crops: [{ id: 'crop-1', name: 'Wheat' }],
  varieties: [{ id: 'variety-1', cropId: 'crop-1', name: 'Durum' }],
  units: [
    { id: 'unit-kg', name: 'Kilogram', baseMeasure: 'mass' },
    { id: 'unit-lb', name: 'Pound', baseMeasure: 'mass' },
    { id: 'unit-oz', name: 'Ounce', baseMeasure: 'mass' },
    { id: 'unit-litre', name: 'Litre', baseMeasure: 'volume' },
  ],
  conversions: [
    { id: 'conv-1', fromUnitId: 'unit-kg', toUnitId: 'unit-lb', factor: 2.2 },
  ],
};

describe.each(implementations)(
  '%s implementation farm setup conformance',
  (_name, make) => {
    let harness: Harness;

    beforeEach(async () => {
      harness = make(FARM_SETUP_SEED);
      await harness.services.auth.login(VALID);
    });

    it('reads the farm and saves an update with the currency normalised', async () => {
      await expect(harness.services.farm.get()).resolves.toEqual({
        id: 'farm-1',
        name: 'Willow Creek Farm',
        reportingCurrency: 'USD',
      });

      const saved = await harness.services.farm.update({
        name: 'Riverbend Farm',
        reportingCurrency: 'eur',
      });
      expect(saved).toEqual({
        id: 'farm-1',
        name: 'Riverbend Farm',
        reportingCurrency: 'EUR',
      });
    });

    it('rejects a blank farm name and an invalid currency', async () => {
      await expect(
        harness.services.farm.update({
          name: '   ',
          reportingCurrency: 'USD',
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'name',
        message: 'Farm name is required.',
      });

      await expect(
        harness.services.farm.update({
          name: 'Farm',
          reportingCurrency: 'dollars',
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'reportingCurrency',
        message: 'Reporting currency must be a three-letter code such as USD.',
      });
    });

    it('rejects a blank field name and saves nothing', async () => {
      await expect(
        harness.services.fields.create({ name: '  ', area: '10' }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'name',
        message: 'Field name is required.',
      });

      await expect(harness.services.fields.list()).resolves.toEqual([]);
    });

    it.each([
      ['-5', 'Area cannot be negative.'],
      ['abc', 'Area must be a number.'],
      ['', 'Area must be a number.'],
    ])('rejects area %s with the backend rule', async (area, message) => {
      await expect(
        harness.services.fields.create({ name: 'South 12', area }),
      ).rejects.toMatchObject({ status: 400, field: 'area', message });

      await expect(harness.services.fields.list()).resolves.toEqual([]);
    });

    it('creates a field and returns it from the list', async () => {
      const created = await harness.services.fields.create({
        name: 'North 40',
        area: '40',
      });

      expect(created).toMatchObject({
        id: expect.any(String),
        name: 'North 40',
        area: 40,
      });
      await expect(harness.services.fields.list()).resolves.toEqual([created]);
    });

    it('requires a base measure category for a new unit', async () => {
      await expect(
        harness.services.units.create({ name: 'Gallon', baseMeasure: '' }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'baseMeasure',
        message:
          'A base measure category (mass, volume, or count) is required.',
      });

      await expect(harness.services.units.list()).resolves.toHaveLength(4);
    });

    it('rejects an unknown base measure category and a duplicate unit', async () => {
      await expect(
        harness.services.units.create({ name: 'Ton', baseMeasure: 'weight' }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'baseMeasure',
        message: 'Base measure must be one of: mass, volume, count.',
      });

      await expect(
        harness.services.units.create({
          name: 'kilogram',
          baseMeasure: 'mass',
        }),
      ).rejects.toMatchObject({ status: 409, field: 'name' });
    });

    it('creates a variety for a crop and lists varieties per crop', async () => {
      const created = await harness.services.varieties.create({
        cropId: 'crop-1',
        name: 'Spelt',
      });

      expect(created).toMatchObject({ cropId: 'crop-1', name: 'Spelt' });
      await expect(harness.services.varieties.list('crop-1')).resolves.toEqual([
        expect.objectContaining({ name: 'Durum' }),
        expect.objectContaining({ name: 'Spelt' }),
      ]);
      await expect(harness.services.varieties.list('crop-2')).resolves.toEqual(
        [],
      );

      await expect(
        harness.services.varieties.create({ cropId: 'missing', name: 'X' }),
      ).rejects.toMatchObject({
        status: 404,
        field: 'cropId',
        message: 'The selected crop does not exist.',
      });
    });

    it('rejects a blank variety name', async () => {
      await expect(
        harness.services.varieties.create({ cropId: 'crop-1', name: ' ' }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'name',
        message: 'Variety name is required.',
      });
    });

    it('adds a conversion rule and converts with it', async () => {
      const rule = await harness.services.conversions.create({
        fromUnitId: 'unit-kg',
        toUnitId: 'unit-oz',
        factor: '35.274',
      });
      expect(rule).toMatchObject({ factor: 35.274 });

      const result = await harness.services.conversions.convert({
        fromUnitId: 'unit-kg',
        toUnitId: 'unit-oz',
        quantity: '2',
      });
      expect(result.converted).toBeCloseTo(70.548);
    });

    it('rejects a non-positive factor and a duplicate rule', async () => {
      await expect(
        harness.services.conversions.create({
          fromUnitId: 'unit-lb',
          toUnitId: 'unit-oz',
          factor: '-2',
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'factor',
        message: 'Conversion factor must be a positive number.',
      });

      await expect(
        harness.services.conversions.create({
          fromUnitId: 'unit-kg',
          toUnitId: 'unit-lb',
          factor: '1',
        }),
      ).rejects.toMatchObject({ status: 409 });
    });

    it("raises the backend's no rule exists error for an unmatched conversion", async () => {
      await expect(
        harness.services.conversions.convert({
          fromUnitId: 'unit-kg',
          toUnitId: 'unit-oz',
          quantity: 5,
        }),
      ).rejects.toMatchObject({
        status: 404,
        message: 'No rule exists for converting from "Kilogram" to "Ounce".',
      });
    });

    it('names the base measure mismatch across categories', async () => {
      await expect(
        harness.services.conversions.convert({
          fromUnitId: 'unit-kg',
          toUnitId: 'unit-litre',
          quantity: 1,
        }),
      ).rejects.toMatchObject({
        status: 400,
        message:
          'Cannot convert "Kilogram" (mass) to "Litre" (volume): base measures do not match.',
      });
    });

    it('converts a unit to itself unchanged', async () => {
      await expect(
        harness.services.conversions.convert({
          fromUnitId: 'unit-kg',
          toUnitId: 'unit-kg',
          quantity: 7,
        }),
      ).resolves.toMatchObject({ factor: 1, converted: 7 });
    });

    it('rejects farm setup requests without a session with 401', async () => {
      const anonymous = make(FARM_SETUP_SEED);

      await expect(anonymous.services.fields.list()).rejects.toMatchObject({
        status: 401,
      });
      await expect(anonymous.services.farm.get()).rejects.toMatchObject({
        status: 401,
      });
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
