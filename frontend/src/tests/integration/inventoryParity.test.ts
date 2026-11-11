import { beforeEach, describe, expect, it } from 'vitest';
import { isLowStock } from '@/services/inventoryRules';
import { createInventoryMock, type InventorySeed } from '@/services/inventoryMock';
import { createHttpServices } from '@/services/httpServices';
import { createMockServices } from '@/services/mockServices';
import { createMemorySessionStore, type SessionStore } from '@/services/sessionStore';
import {
  isApiError,
  type AgrivantaServices,
  type InventoryItemInput,
  type StockMovementInput,
  type StockMovementType,
  type Unit,
  type User,
} from '@/services/types';

const BASE_URL = 'https://api.agrivanta.test/v1';
const VALID = { email: 'owner@agrivanta.test', password: 'password123' };
const TEST_USER: User = {
  id: 'user-owner',
  email: VALID.email,
  role: 'owner',
};

const UNITS: Unit[] = [
  { id: 'unit-kg', name: 'Kilogram', baseMeasure: 'mass' },
  { id: 'unit-litre', name: 'Litre', baseMeasure: 'volume' },
];

const INVENTORY_SEED: InventorySeed = {
  items: [
    { id: 'item-1', name: 'Urea', unitId: 'unit-kg', reorderLevel: 20 },
    { id: 'item-2', name: 'Diesel', unitId: 'unit-litre', reorderLevel: 0 },
  ],
  movements: [
    { id: 'movement-1', itemId: 'item-1', type: 'purchase', quantity: 100 },
    { id: 'movement-2', itemId: 'item-1', type: 'usage', quantity: 30 },
  ],
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
 * Minimal in-memory stand-in for backend issue #16 so the HTTP
 * implementation can be exercised with the same expectations as the mock.
 * The inventory endpoints delegate to the shared mock engine (with auth
 * enforced here at the HTTP boundary) so both implementations are held to
 * one rule set.
 */
function createFakeBackend(seed?: InventorySeed): FakeBackend {
  const requests: RecordedRequest[] = [];
  const inventory = createInventoryMock({
    seed,
    requireAuth: () => undefined,
    findUnit: async (id) => UNITS.find((unit) => unit.id === id) ?? null,
  });

  async function fetchFn(
    input: string,
    init: RequestInit = {},
  ): Promise<Response> {
    requests.push({ url: input, init });

    const path = new URL(input).pathname;
    const method = init.method ?? 'GET';

    if (!readTokenHeader(init)) {
      return json({ detail: 'Unauthorized' }, 401);
    }

    const payload: unknown = init.body ? JSON.parse(String(init.body)) : {};
    const movementsMatch = /\/inventory-items\/([^/]+)\/movements$/.exec(path);

    try {
      if (movementsMatch) {
        const itemId = decodeURIComponent(movementsMatch[1]);

        if (method === 'GET') {
          return json(await inventory.movements.list(itemId));
        }

        if (method === 'POST') {
          return json(
            await inventory.movements.create({
              ...(payload as StockMovementInput),
              itemId,
            }),
            201,
          );
        }
      }

      if (path.endsWith('/stock-movements') && method === 'GET') {
        return json(await inventory.movements.list());
      }

      if (path.endsWith('/inventory-items')) {
        if (method === 'GET') {
          return json(await inventory.items.list());
        }

        if (method === 'POST') {
          return json(
            await inventory.items.create(payload as InventoryItemInput),
            201,
          );
        }
      }

      const itemMatch = /\/inventory-items\/([^/]+)$/.exec(path);

      if (itemMatch && method === 'PUT') {
        return json(
          await inventory.items.update(
            decodeURIComponent(itemMatch[1]),
            payload as InventoryItemInput,
          ),
        );
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

  return { fetchFn, requests };
}

interface Harness {
  services: AgrivantaServices;
  store: SessionStore;
  requests: RecordedRequest[];
}

type MakeHarness = (
  seed?: InventorySeed,
  authenticated?: boolean,
) => Promise<Harness>;

const implementations: Array<[string, MakeHarness]> = [
  [
    'mock',
    async (seed, authenticated = true) => {
      const store = createMemorySessionStore();
      const services = createMockServices({
        store,
        farmSetup: { units: UNITS },
        inventory: seed,
      });

      if (authenticated) {
        await services.auth.login(VALID);
      }

      return { services, store, requests: [] };
    },
  ],
  [
    'http',
    async (seed, authenticated = true) => {
      const store = createMemorySessionStore();

      if (authenticated) {
        store.save({ token: 'token-test', user: TEST_USER });
      }

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
  '%s implementation inventory conformance',
  (_name, make) => {
    let harness: Harness;

    beforeEach(async () => {
      harness = await make(INVENTORY_SEED);
    });

    it('derives each item current quantity from its movements', async () => {
      await expect(harness.services.items.list()).resolves.toEqual([
        {
          id: 'item-1',
          name: 'Urea',
          unitId: 'unit-kg',
          reorderLevel: 20,
          currentQuantity: 70,
        },
        {
          id: 'item-2',
          name: 'Diesel',
          unitId: 'unit-litre',
          reorderLevel: 0,
          currentQuantity: 0,
        },
      ]);
    });

    it('creates an item and lists it with quantity zero', async () => {
      const created = await harness.services.items.create({
        name: ' DAP ',
        unitId: 'unit-kg',
        reorderLevel: '15',
      });

      expect(created).toEqual({
        id: expect.any(String),
        name: 'DAP',
        unitId: 'unit-kg',
        reorderLevel: 15,
        currentQuantity: 0,
      });
      await expect(harness.services.items.list()).resolves.toHaveLength(3);
    });

    it('rejects a blank item name and saves nothing', async () => {
      await expect(
        harness.services.items.create({
          name: '   ',
          unitId: 'unit-kg',
          reorderLevel: 5,
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'name',
        message: 'Inventory item name is required.',
      });

      await expect(harness.services.items.list()).resolves.toHaveLength(2);
    });

    it('requires an existing unit for an item', async () => {
      await expect(
        harness.services.items.create({
          name: 'Seed',
          unitId: '',
          reorderLevel: 5,
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'unitId',
        message: 'Select a unit.',
      });

      await expect(
        harness.services.items.create({
          name: 'Seed',
          unitId: 'missing',
          reorderLevel: 5,
        }),
      ).rejects.toMatchObject({
        status: 404,
        field: 'unitId',
        message: 'That unit does not exist.',
      });
    });

    it.each([
      ['-5', 'Reorder level cannot be negative.'],
      ['abc', 'Reorder level must be a number.'],
      ['', 'Reorder level must be a number.'],
    ])(
      'rejects reorder level %s with the backend rule',
      async (value, message) => {
        await expect(
          harness.services.items.create({
            name: 'Seed',
            unitId: 'unit-kg',
            reorderLevel: value,
          }),
        ).rejects.toMatchObject({
          status: 400,
          field: 'reorderLevel',
          message,
        });

        await expect(harness.services.items.list()).resolves.toHaveLength(2);
      },
    );

    it('purchases increase and usages decrease the derived quantity', async () => {
      await harness.services.movements.create({
        itemId: 'item-2',
        type: 'purchase',
        quantity: '40',
      });

      let items = await harness.services.items.list();
      expect(items.find((item) => item.id === 'item-2')).toMatchObject({
        currentQuantity: 40,
      });

      await harness.services.movements.create({
        itemId: 'item-2',
        type: 'usage',
        quantity: '15',
      });

      items = await harness.services.items.list();
      expect(items.find((item) => item.id === 'item-2')).toMatchObject({
        currentQuantity: 25,
      });
    });

    it('signed adjustments increase or decrease the derived quantity', async () => {
      await harness.services.movements.create({
        itemId: 'item-2',
        type: 'adjustment',
        quantity: 10,
      });
      await harness.services.movements.create({
        itemId: 'item-2',
        type: 'adjustment',
        quantity: -3,
      });

      const diesel = (await harness.services.items.list()).find(
        (item) => item.id === 'item-2',
      );
      expect(diesel?.currentQuantity).toBe(7);
    });

    it('rejects a usage that would drive the quantity below zero', async () => {
      await expect(
        harness.services.movements.create({
          itemId: 'item-2',
          type: 'usage',
          quantity: '5',
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'quantity',
        message: 'Usage exceeds the available quantity (available: 0).',
      });

      await expect(harness.services.items.list()).resolves.toHaveLength(2);
    });

    it('rejects non-positive and non-numeric movement quantities', async () => {
      await expect(
        harness.services.movements.create({
          itemId: 'item-2',
          type: 'purchase',
          quantity: '0',
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'quantity',
        message: 'Quantity must be a positive number.',
      });

      await expect(
        harness.services.movements.create({
          itemId: 'item-2',
          type: 'usage',
          quantity: '-5',
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'quantity',
        message: 'Quantity must be a positive number.',
      });

      await expect(
        harness.services.movements.create({
          itemId: 'item-2',
          type: 'purchase',
          quantity: 'abc',
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'quantity',
        message: 'Quantity must be a number.',
      });

      await expect(
        harness.services.movements.create({
          itemId: 'item-2',
          type: 'adjustment',
          quantity: '0',
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'quantity',
        message: 'Adjustment quantity cannot be zero.',
      });
    });

    it('rejects unknown items, invalid movement types, and unknown update targets', async () => {
      await expect(
        harness.services.movements.create({
          itemId: 'missing',
          type: 'purchase',
          quantity: 1,
        }),
      ).rejects.toMatchObject({
        status: 404,
        field: 'itemId',
        message: 'That inventory item does not exist.',
      });

      await expect(
        harness.services.movements.create({
          itemId: 'item-1',
          type: 'sale' as unknown as StockMovementType,
          quantity: 1,
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'type',
        message: 'Movement type must be one of: purchase, usage, adjustment.',
      });

      await expect(
        harness.services.items.update('missing', {
          name: 'X',
          unitId: 'unit-kg',
          reorderLevel: 1,
        }),
      ).rejects.toMatchObject({
        status: 404,
        message: 'That inventory item no longer exists.',
      });
    });

    it('updates an item while keeping its derived quantity', async () => {
      const updated = await harness.services.items.update('item-1', {
        name: 'Urea 46',
        unitId: 'unit-kg',
        reorderLevel: 50,
      });

      expect(updated).toEqual({
        id: 'item-1',
        name: 'Urea 46',
        unitId: 'unit-kg',
        reorderLevel: 50,
        currentQuantity: 70,
      });
    });

    it('lists movements for one item or across items', async () => {
      await harness.services.movements.create({
        itemId: 'item-2',
        type: 'purchase',
        quantity: 10,
      });

      await expect(
        harness.services.movements.list('item-1'),
      ).resolves.toHaveLength(2);
      await expect(harness.services.movements.list('item-2')).resolves.toEqual([
        expect.objectContaining({
          itemId: 'item-2',
          type: 'purchase',
          quantity: 10,
        }),
      ]);
      await expect(harness.services.movements.list()).resolves.toHaveLength(3);
    });

    it('flags low stock at or below the reorder level', async () => {
      const items = await harness.services.items.list();
      const urea = items.find((item) => item.id === 'item-1');
      const diesel = items.find((item) => item.id === 'item-2');

      expect(urea).toBeDefined();
      expect(diesel).toBeDefined();
      expect(isLowStock(urea!)).toBe(false);
      expect(isLowStock(diesel!)).toBe(true);
      expect(isLowStock({ currentQuantity: 20, reorderLevel: 20 })).toBe(true);
      expect(isLowStock({ currentQuantity: 0, reorderLevel: 0 })).toBe(true);
      expect(isLowStock({ currentQuantity: 5, reorderLevel: 0 })).toBe(false);
    });

    it('rejects inventory requests without a session with 401', async () => {
      const anonymous = await make(INVENTORY_SEED, false);

      await expect(anonymous.services.items.list()).rejects.toMatchObject({
        status: 401,
      });
      await expect(anonymous.services.movements.list()).rejects.toMatchObject({
        status: 401,
      });
    });
  },
);

describe('inventory HTTP routes', () => {
  it('calls the backend routes the inventory domain exposes', async () => {
    const store = createMemorySessionStore();
    store.save({ token: 'token-test', user: TEST_USER });
    const backend = createFakeBackend(INVENTORY_SEED);
    const services = createHttpServices({
      baseUrl: BASE_URL,
      store,
      fetchFn: backend.fetchFn,
    });

    await services.items.list();
    await services.items.create({
      name: 'Compost',
      unitId: 'unit-kg',
      reorderLevel: 1,
    });
    await services.items.update('item-1', {
      name: 'Urea',
      unitId: 'unit-kg',
      reorderLevel: 20,
    });
    await services.movements.list('item-1');
    await services.movements.list();
    await services.movements.create({
      itemId: 'item-1',
      type: 'purchase',
      quantity: 5,
    });

    expect(
      backend.requests.map(
        ({ url, init }) => `${init?.method ?? 'GET'} ${new URL(url).pathname}`,
      ),
    ).toEqual([
      'GET /v1/inventory-items',
      'POST /v1/inventory-items',
      'PUT /v1/inventory-items/item-1',
      'GET /v1/inventory-items/item-1/movements',
      'GET /v1/stock-movements',
      'POST /v1/inventory-items/item-1/movements',
    ]);
  });
});
