import { beforeEach, describe, expect, it } from 'vitest';
import { createHttpServices } from '@/services/httpServices';
import { HARVEST_ERRORS, SALE_ERRORS } from '@/services/harvestSaleRules';
import { createHarvestSaleMock, type HarvestSaleSeed } from '@/services/harvestSaleMock';
import { createMockServices } from '@/services/mockServices';
import { createMemorySessionStore, type SessionStore } from '@/services/sessionStore';
import {
  isApiError,
  type AgrivantaServices,
  type HarvestInput,
  type SaleInput,
  type User,
} from '@/services/types';

const BASE_URL = 'https://api.agrivanta.test/v1';
const VALID = { email: 'owner@agrivanta.test', password: 'password123' };

const DAY = '2026-03-01';

const HARVEST_SALE_SEED: HarvestSaleSeed = {
  cycles: [
    { id: 'cycle-1', label: 'North 40 — Wheat 2026', status: 'open' },
    { id: 'cycle-2', label: 'South 12 — Maize 2026', status: 'open' },
  ],
  customers: [
    { id: 'customer-1', name: 'Greenfield Grain Co.' },
    { id: 'customer-2', name: 'Harbour Mill' },
  ],
  harvests: [
    {
      id: 'harvest-1',
      cycleId: 'cycle-1',
      quantity: 100,
      unitId: 'unit-kg',
      date: DAY,
    },
    {
      id: 'harvest-2',
      cycleId: 'cycle-2',
      quantity: 20,
      unitId: 'unit-kg',
      date: DAY,
    },
  ],
  sales: [],
};

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
 * Minimal in-memory stand-in for the backend so the HTTP implementation runs
 * against the same rule engine as the mock. Route handling mirrors the real
 * REST endpoints the HTTP client calls.
 */
function createFakeBackend(seed?: HarvestSaleSeed): FakeBackend {
  const users = new Map<string, { password: string; user: User }>();
  users.set(VALID.email, {
    password: VALID.password,
    user: { id: 'user-owner', email: VALID.email, role: 'owner' },
  });
  const sessions = new Map<string, User>();
  const requests: RecordedRequest[] = [];
  const domain = createHarvestSaleMock({
    seed,
    requireAuth: () => undefined,
  });

  async function fetchFn(
    input: string,
    init: RequestInit = {},
  ): Promise<Response> {
    requests.push({ url: input, init });

    const url = new URL(input);
    const path = url.pathname;
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

    const token = readTokenHeader(init);

    if (!token || !sessions.has(token)) {
      return json({ detail: 'Unauthorized' }, 401);
    }

    const payload: unknown = init.body ? JSON.parse(String(init.body)) : {};

    try {
      if (method === 'GET' && path.endsWith('/harvests/cycles')) {
        return json(await domain.harvests.listCycles());
      }

      if (method === 'GET' && /\/harvests$/.test(path)) {
        const cycle = url.searchParams.get('cycle');
        return json(await domain.harvests.list(cycle ?? undefined));
      }

      if (method === 'POST' && /\/harvests$/.test(path)) {
        return json(await domain.harvests.create(payload as HarvestInput), 201);
      }

      if (method === 'GET' && /\/sales$/.test(path)) {
        return json(await domain.sales.list());
      }

      if (method === 'POST' && /\/sales$/.test(path)) {
        return json(await domain.sales.create(payload as SaleInput), 201);
      }

      if (method === 'GET' && /\/customers$/.test(path)) {
        return json(await domain.sales.listCustomers());
      }
    } catch (error) {
      if (isApiError(error)) {
        return json(
          { detail: error.message, field: error.field },
          error.status,
        );
      }
      throw error;
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

type MakeHarness = (seed?: HarvestSaleSeed) => Harness;

const implementations: Array<[string, MakeHarness]> = [
  [
    'mock',
    (seed) => {
      const store = createMemorySessionStore();
      return {
        services: createMockServices({ store, harvestSale: seed }),
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
  '%s implementation harvest and sale conformance',
  (_name, make) => {
    let harness: Harness;
    let loggedIn: Harness;

    beforeEach(async () => {
      harness = make(HARVEST_SALE_SEED);
      loggedIn = make(HARVEST_SALE_SEED);
      await loggedIn.services.auth.login(VALID);
    });

    it('lists the crop cycles and a cycle\u2019s harvests', async () => {
      await expect(loggedIn.services.harvests.listCycles()).resolves.toEqual([
        { id: 'cycle-1', label: 'North 40 — Wheat 2026' },
        { id: 'cycle-2', label: 'South 12 — Maize 2026' },
      ]);

      await expect(loggedIn.services.harvests.list('cycle-1')).resolves.toEqual(
        [expect.objectContaining({ id: 'harvest-1' })],
      );
      await expect(loggedIn.services.harvests.list()).resolves.toHaveLength(2);
    });

    it('records a harvest and returns it from the cycle\u2019s list', async () => {
      const created = await loggedIn.services.harvests.create({
        cycleId: 'cycle-2',
        quantity: '25',
        unitId: 'unit-kg',
        date: '2026-04-01',
      });

      expect(created).toEqual(
        expect.objectContaining({
          id: expect.any(String),
          cycleId: 'cycle-2',
          quantity: 25,
          unitId: 'unit-kg',
          date: '2026-04-01',
        }),
      );

      await expect(loggedIn.services.harvests.list('cycle-2')).resolves.toEqual(
        [
          expect.objectContaining({ id: 'harvest-2' }),
          expect.objectContaining({ id: created.id, quantity: 25 }),
        ],
      );
    });

    it('rejects a blank harvest quantity with an inline field and saves nothing', async () => {
      await expect(
        loggedIn.services.harvests.create({
          cycleId: 'cycle-1',
          quantity: '',
          unitId: 'unit-kg',
          date: DAY,
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'quantity',
        message: HARVEST_ERRORS.quantityRequired,
      });

      await expect(
        loggedIn.services.harvests.list('cycle-1'),
      ).resolves.toHaveLength(1);
    });

    it('rejects a blank harvest date with an inline field', async () => {
      await expect(
        loggedIn.services.harvests.create({
          cycleId: 'cycle-1',
          quantity: '5',
          unitId: 'unit-kg',
          date: '',
        }),
      ).rejects.toMatchObject({ status: 400, field: 'date' });
    });

    it('rejects zero or negative harvest quantities', async () => {
      for (const quantity of ['0', '-5']) {
        await expect(
          loggedIn.services.harvests.create({
            cycleId: 'cycle-1',
            quantity,
            unitId: 'unit-kg',
            date: DAY,
          }),
        ).rejects.toMatchObject({
          status: 400,
          field: 'quantity',
          message: HARVEST_ERRORS.quantityNotPositive,
        });
      }
    });

    it('rejects a harvest without a unit or cycle', async () => {
      await expect(
        loggedIn.services.harvests.create({
          cycleId: 'cycle-1',
          quantity: '5',
          unitId: '',
          date: DAY,
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'unitId',
        message: HARVEST_ERRORS.unitRequired,
      });

      await expect(
        loggedIn.services.harvests.create({
          cycleId: 'cycle-unknown',
          quantity: '5',
          unitId: 'unit-kg',
          date: DAY,
        }),
      ).rejects.toMatchObject({
        status: 404,
        field: 'cycleId',
        message: HARVEST_ERRORS.cycleNotFound,
      });
    });

    it('rejects a harvest on a closed crop cycle', async () => {
      const closed = make({
        ...HARVEST_SALE_SEED,
        cycles: [
          { id: 'cycle-closed', label: 'Closed cycle', status: 'closed' },
        ],
      });
      await closed.services.auth.login(VALID);

      await expect(
        closed.services.harvests.create({
          cycleId: 'cycle-closed',
          quantity: '5',
          unitId: 'unit-kg',
          date: DAY,
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'cycleId',
        message: HARVEST_ERRORS.cycleClosed,
      });

      await expect(
        closed.services.harvests.list('cycle-closed'),
      ).resolves.toEqual([]);
    });

    it('lists the customer profiles the sale form offers', async () => {
      await expect(loggedIn.services.sales.listCustomers()).resolves.toEqual([
        { id: 'customer-1', name: 'Greenfield Grain Co.' },
        { id: 'customer-2', name: 'Harbour Mill' },
      ]);
    });

    it('records a sale with revenue equal to quantity \u00d7 unit price', async () => {
      const created = await loggedIn.services.sales.create({
        customerId: 'customer-1',
        harvestId: 'harvest-1',
        quantity: '10',
        unitPrice: '3.5',
        date: DAY,
      });

      expect(created).toEqual(
        expect.objectContaining({
          customerId: 'customer-1',
          harvestId: 'harvest-1',
          quantity: 10,
          unitPrice: 3.5,
          revenue: 35,
        }),
      );

      await expect(loggedIn.services.sales.list()).resolves.toEqual([
        expect.objectContaining({ id: created.id, revenue: 35 }),
      ]);
    });

    it('rejects a sale above the remaining unsold quantity on the quantity field', async () => {
      await loggedIn.services.sales.create({
        customerId: 'customer-1',
        harvestId: 'harvest-1',
        quantity: '60',
        unitPrice: '3.5',
        date: DAY,
      });

      await expect(
        loggedIn.services.sales.create({
          customerId: 'customer-2',
          harvestId: 'harvest-1',
          quantity: '50',
          unitPrice: '3.5',
          date: DAY,
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'quantity',
        message: SALE_ERRORS.soldExceedsHarvested(40),
      });

      await expect(loggedIn.services.sales.list()).resolves.toHaveLength(1);

      // Exactly the remaining quantity (40 of 100, 60 already sold) succeeds.
      await expect(
        loggedIn.services.sales.create({
          customerId: 'customer-2',
          harvestId: 'harvest-1',
          quantity: '40',
          unitPrice: '3.5',
          date: DAY,
        }),
      ).resolves.toEqual(expect.objectContaining({ quantity: 40 }));
    });

    it('rejects a blank sale quantity or date with the offending field', async () => {
      const input = {
        customerId: 'customer-1',
        harvestId: 'harvest-1',
        quantity: '10',
        unitPrice: '3.5',
        date: DAY,
      };

      await expect(
        loggedIn.services.sales.create({ ...input, quantity: '' }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'quantity',
        message: SALE_ERRORS.quantityRequired,
      });

      await expect(
        loggedIn.services.sales.create({ ...input, date: '' }),
      ).rejects.toMatchObject({ status: 400, field: 'date' });

      await expect(loggedIn.services.sales.list()).resolves.toEqual([]);
    });

    it('rejects a non-positive sale quantity or unit price', async () => {
      const input = {
        customerId: 'customer-1',
        harvestId: 'harvest-1',
        quantity: '10',
        unitPrice: '3.5',
        date: DAY,
      };

      await expect(
        loggedIn.services.sales.create({ ...input, quantity: '0' }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'quantity',
        message: SALE_ERRORS.quantityNotPositive,
      });

      await expect(
        loggedIn.services.sales.create({ ...input, unitPrice: '-1' }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'unitPrice',
        message: SALE_ERRORS.unitPriceNotPositive,
      });
    });

    it('rejects an unknown customer or harvest', async () => {
      const input = {
        customerId: 'customer-1',
        harvestId: 'harvest-1',
        quantity: '10',
        unitPrice: '3.5',
        date: DAY,
      };

      await expect(
        loggedIn.services.sales.create({ ...input, customerId: 'nope' }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'customerId',
        message: SALE_ERRORS.customerNotFound,
      });

      await expect(
        loggedIn.services.sales.create({ ...input, harvestId: 'nope' }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'harvestId',
        message: SALE_ERRORS.harvestNotFound,
      });
    });

    it('rejects harvest and sale requests without a session', async () => {
      await expect(
        harness.services.harvests.listCycles(),
      ).rejects.toMatchObject({ status: 401 });
      await expect(harness.services.sales.list()).rejects.toMatchObject({
        status: 401,
      });
    });
  },
);
