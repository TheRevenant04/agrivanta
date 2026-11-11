import { beforeEach, describe, expect, it } from 'vitest';
import { createCropCycleMock } from '@/services/cropCycleMock';
import { createHttpServices } from '@/services/httpServices';
import { createMockServices } from '@/services/mockServices';
import { createMemorySessionStore, type SessionStore } from '@/services/sessionStore';
import {
  isApiError,
  type AgrivantaServices,
  type CropCycle,
  type CropCycleInput,
  type CropCycleUpdateInput,
  type User,
} from '@/services/types';

const BASE_URL = 'https://api.agrivanta.test/v1';
const VALID = { email: 'owner@agrivanta.test', password: 'password123' };
const OWNER: User = {
  id: 'user-owner',
  email: VALID.email,
  role: 'owner',
};

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
 * Minimal in-memory stand-in for the backend's crop cycle endpoints so the
 * HTTP implementation can be exercised with the same expectations as the
 * mock. Routes delegate to the shared mock engine (with auth enforced here
 * at the HTTP boundary) so both implementations are held to one rule set.
 */
function createCropCycleBackend(seed?: CropCycle[]): {
  fetchFn: (input: string, init?: RequestInit) => Promise<Response>;
} {
  const sessions = new Map<string, User>([['token-owner', OWNER]]);
  const cycles = createCropCycleMock({ seed, requireAuth: () => undefined });

  async function fetchFn(
    input: string,
    init: RequestInit = {},
  ): Promise<Response> {
    const url = new URL(input);
    const path = url.pathname;
    const method = init.method ?? 'GET';

    if (method === 'POST' && path.endsWith('/auth/login')) {
      return json({ token: 'token-owner', user: OWNER });
    }

    const match = /\/crop-cycles(?:\/([^/]+))?(?:\/close)?$/.exec(path);

    if (!match) {
      return json({ detail: 'Not found' }, 404);
    }

    const [, id] = match;
    const token = readTokenHeader(init);

    if (!token || !sessions.has(token)) {
      return json({ detail: 'Unauthorized' }, 401);
    }

    const payload: CropCycleInput | CropCycleUpdateInput = init.body
      ? (JSON.parse(String(init.body)) as CropCycleInput)
      : {};

    try {
      if (!id && method === 'GET') {
        const field = url.searchParams.get('field');
        return json(await cycles.cropCycles.list(field ?? undefined));
      }
      if (!id && method === 'POST') {
        return json(
          await cycles.cropCycles.create(payload as CropCycleInput),
          201,
        );
      }
      if (id && method === 'PUT') {
        return json(
          await cycles.cropCycles.update(id, payload as CropCycleUpdateInput),
        );
      }
      if (id && method === 'POST' && path.endsWith('/close')) {
        return json(await cycles.cropCycles.close(id));
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

  return { fetchFn };
}

const SEED: CropCycle[] = [
  {
    id: 'cycle-1',
    fieldId: 'field-1',
    cropId: 'crop-1',
    varietyId: 'variety-1',
    startDate: '2026-03-01',
    endDate: '2026-07-15',
    status: 'open',
    expectedYield: 12,
    expectedPrice: 250,
  },
  {
    id: 'cycle-2',
    fieldId: 'field-2',
    cropId: 'crop-2',
    varietyId: 'variety-3',
    startDate: '2026-05-01',
    status: 'open',
  },
];

interface Harness {
  services: AgrivantaServices;
  store: SessionStore;
}

type MakeHarness = (seed?: CropCycle[]) => Harness;

const implementations: Array<[string, MakeHarness]> = [
  [
    'mock',
    (seed) => {
      const store = createMemorySessionStore();
      return {
        services: createMockServices({ store, cropCycles: seed }),
        store,
      };
    },
  ],
  [
    'http',
    (seed) => {
      const store = createMemorySessionStore();
      const backend = createCropCycleBackend(seed);
      return {
        services: createHttpServices({
          baseUrl: BASE_URL,
          store,
          fetchFn: backend.fetchFn,
        }),
        store,
      };
    },
  ],
];

describe.each(implementations)(
  '%s implementation crop cycle conformance',
  (_name, make) => {
    let harness: Harness;

    beforeEach(async () => {
      harness = make(SEED);
      await harness.services.auth.login(VALID);
    });

    it('rejects crop cycle requests without a session with 401', async () => {
      const anonymous = make(SEED);

      await expect(anonymous.services.cropCycles.list()).rejects.toMatchObject({
        status: 401,
      });
      await expect(
        anonymous.services.cropCycles.create({
          fieldId: 'field-1',
          cropId: 'crop-1',
          varietyId: 'variety-1',
          startDate: '2026-03-01',
        }),
      ).rejects.toMatchObject({ status: 401 });
    });

    it('lists every cycle and filters by field', async () => {
      await expect(harness.services.cropCycles.list()).resolves.toEqual([
        expect.objectContaining({ id: 'cycle-1', fieldId: 'field-1' }),
        expect.objectContaining({ id: 'cycle-2', fieldId: 'field-2' }),
      ]);

      await expect(
        harness.services.cropCycles.list('field-1'),
      ).resolves.toEqual([
        expect.objectContaining({ id: 'cycle-1', fieldId: 'field-1' }),
      ]);
      await expect(
        harness.services.cropCycles.list('field-missing'),
      ).resolves.toEqual([]);
    });

    it('returns an empty list when the field has no cycles', async () => {
      const empty = make([]);
      await empty.services.auth.login(VALID);

      await expect(empty.services.cropCycles.list()).resolves.toEqual([]);
      await expect(empty.services.cropCycles.list('field-1')).resolves.toEqual(
        [],
      );
    });

    it('keeps two overlapping cycles on the same field in the list', async () => {
      const created = await harness.services.cropCycles.create({
        fieldId: 'field-1',
        cropId: 'crop-2',
        varietyId: 'variety-3',
        startDate: '2026-05-01',
        endDate: '2026-09-01',
      });

      const listed = await harness.services.cropCycles.list('field-1');
      expect(listed).toHaveLength(2);
      expect(listed).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ id: 'cycle-1', status: 'open' }),
          expect.objectContaining({ id: created.id, status: 'open' }),
        ]),
      );
    });

    it('creates a cycle that starts open and carries the parsed values', async () => {
      const created = await harness.services.cropCycles.create({
        fieldId: 'field-1',
        cropId: 'crop-1',
        varietyId: 'variety-1',
        startDate: '2026-04-01',
        endDate: '2026-08-01',
        expectedYield: '10.5',
        expectedPrice: '200',
      });

      expect(created).toMatchObject({
        id: expect.any(String),
        fieldId: 'field-1',
        cropId: 'crop-1',
        varietyId: 'variety-1',
        startDate: '2026-04-01',
        endDate: '2026-08-01',
        expectedYield: 10.5,
        expectedPrice: 200,
        status: 'open',
      });

      await expect(
        harness.services.cropCycles.list('field-1'),
      ).resolves.toEqual(
        expect.arrayContaining([expect.objectContaining({ id: created.id })]),
      );
    });

    it('rejects a blank start date and saves nothing', async () => {
      await expect(
        harness.services.cropCycles.create({
          fieldId: 'field-1',
          cropId: 'crop-1',
          varietyId: 'variety-1',
          startDate: '   ',
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'startDate',
        message: 'Start date is required.',
      });

      await expect(
        harness.services.cropCycles.list('field-1'),
      ).resolves.toEqual([expect.objectContaining({ id: 'cycle-1' })]);
    });

    it.each([
      ['fieldId', 'Select a field for this crop cycle.'],
      ['cropId', 'Select a crop for this crop cycle.'],
      ['varietyId', 'Select a variety for this crop cycle.'],
    ] as const)('rejects a blank %s on create', async (field, message) => {
      const input: CropCycleInput = {
        fieldId: 'field-1',
        cropId: 'crop-1',
        varietyId: 'variety-1',
        startDate: '2026-04-01',
      };
      input[field] = '   ';

      await expect(
        harness.services.cropCycles.create(input),
      ).rejects.toMatchObject({ status: 400, field, message });
    });

    it.each([
      ['2026-02-31', 'Start date must be a valid calendar date.'],
      ['tomorrow', 'Start date must be a valid calendar date.'],
    ])('rejects the start date %s', async (startDate, message) => {
      await expect(
        harness.services.cropCycles.create({
          fieldId: 'field-1',
          cropId: 'crop-1',
          varietyId: 'variety-1',
          startDate,
        }),
      ).rejects.toMatchObject({ status: 400, field: 'startDate', message });
    });

    it('rejects an end date before the start date', async () => {
      await expect(
        harness.services.cropCycles.create({
          fieldId: 'field-1',
          cropId: 'crop-1',
          varietyId: 'variety-1',
          startDate: '2026-04-01',
          endDate: '2026-03-01',
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'endDate',
        message: 'End date cannot be before the start date.',
      });
    });

    it('saves an expected yield and price update on an open cycle', async () => {
      const updated = await harness.services.cropCycles.update('cycle-1', {
        expectedYield: '15',
        expectedPrice: 300,
      });

      expect(updated).toMatchObject({
        id: 'cycle-1',
        expectedYield: 15,
        expectedPrice: 300,
      });

      await expect(
        harness.services.cropCycles.list('field-1'),
      ).resolves.toEqual([
        expect.objectContaining({
          id: 'cycle-1',
          expectedYield: 15,
          expectedPrice: 300,
        }),
      ]);
    });

    it.each([
      ['abc', 'Expected yield must be a number.', 'expectedYield'],
      ['-1', 'Expected yield cannot be negative.', 'expectedYield'],
      ['abc', 'Expected price must be a number.', 'expectedPrice'],
      ['-2', 'Expected price cannot be negative.', 'expectedPrice'],
    ])(
      'rejects the expected amount %s with the backend rule',
      async (value, message, field) => {
        const input: CropCycleUpdateInput =
          field === 'expectedYield'
            ? { expectedYield: value }
            : { expectedPrice: value };

        await expect(
          harness.services.cropCycles.update('cycle-1', input),
        ).rejects.toMatchObject({ status: 400, field, message });
      },
    );

    it('closes a cycle, locks it against edits, and rejects a second close', async () => {
      const closed = await harness.services.cropCycles.close('cycle-1');
      expect(closed).toMatchObject({ id: 'cycle-1', status: 'closed' });

      await expect(
        harness.services.cropCycles.update('cycle-1', { expectedYield: '1' }),
      ).rejects.toMatchObject({
        status: 409,
        message: 'This crop cycle is closed and can no longer be edited.',
      });

      await expect(
        harness.services.cropCycles.close('cycle-1'),
      ).rejects.toMatchObject({
        status: 409,
        message: 'This crop cycle is already closed.',
      });

      await expect(
        harness.services.cropCycles.list('field-1'),
      ).resolves.toEqual([
        expect.objectContaining({ id: 'cycle-1', status: 'closed' }),
      ]);
    });

    it('raises 404 for an unknown cycle', async () => {
      await expect(
        harness.services.cropCycles.close('cycle-missing'),
      ).rejects.toMatchObject({ status: 404 });
      await expect(
        harness.services.cropCycles.update('cycle-missing', {
          expectedYield: '1',
        }),
      ).rejects.toMatchObject({ status: 404 });
    });
  },
);
