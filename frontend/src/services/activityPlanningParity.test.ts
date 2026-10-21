import { beforeEach, describe, expect, it } from 'vitest';
import {
  createActivityPlanningMock,
  DEFAULT_PLANNING_CYCLES,
  type ActivityPlanningSeed,
} from './activityPlanningMock';
import { createHttpServices } from './httpServices';
import { createMockServices } from './mockServices';
import { createMemorySessionStore, type SessionStore } from './sessionStore';
import {
  isApiError,
  type AgrivantaServices,
  type ActivityInput,
  type ActivityType,
  type ResourceNeedsInput,
  type User,
} from './types';

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
 * In-memory stand-in for the activity planning endpoints so the HTTP
 * implementation can be exercised with the same expectations as the mock.
 * Routes delegate to the shared mock engine (with auth enforced here at
 * the HTTP boundary) so both implementations are held to one rule set.
 */
function createFakeBackend(seed?: ActivityPlanningSeed): FakeBackend {
  const users = new Map<string, { password: string; user: User }>();
  users.set(VALID.email, {
    password: VALID.password,
    user: { id: 'user-owner', email: VALID.email, role: 'owner' },
  });
  const sessions = new Map<string, User>();
  const requests: RecordedRequest[] = [];
  const planning = createActivityPlanningMock({
    seed,
    requireAuth: () => undefined,
  });

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

    const token = readTokenHeader(init);

    if (!token || !sessions.has(token)) {
      return json({ detail: 'Unauthorized' }, 401);
    }

    const payload: unknown = init.body ? JSON.parse(String(init.body)) : {};

    if (path.endsWith('/activity-types')) {
      try {
        if (method === 'GET') {
          return json(await planning.activityTypes.list());
        }
        if (method === 'POST') {
          return json(
            await planning.activityTypes.create(payload as ActivityType),
            201,
          );
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
    }

    if (path.endsWith('/activities/cycles') && method === 'GET') {
      return json(await planning.activities.listCycles());
    }

    if (path.endsWith('/resource-needs') && method === 'PUT') {
      const id = path.split('/').at(-2) ?? '';

      try {
        return json(
          await planning.activities.updateResourceNeeds(
            id,
            payload as ResourceNeedsInput,
          ),
        );
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

    if (path.endsWith('/status') && method === 'PUT') {
      const id = path.split('/').at(-2) ?? '';
      const status = (payload as { status?: unknown }).status;

      try {
        return json(
          await planning.activities.updateStatus(
            id,
            typeof status === 'string' ? status : '',
          ),
        );
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

    if (path.endsWith('/activities')) {
      try {
        if (method === 'GET') {
          const cycle = new URL(input).searchParams.get('cycle');
          return json(await planning.activities.list(cycle ?? undefined));
        }
        if (method === 'POST') {
          return json(
            await planning.activities.create(payload as ActivityInput),
            201,
          );
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
    }

    const activityMatch = /\/activities\/([^/]+)$/.exec(path);

    if (activityMatch && method === 'PUT') {
      try {
        return json(
          await planning.activities.update(
            activityMatch[1],
            payload as ActivityInput,
          ),
        );
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
}

type MakeHarness = (seed?: ActivityPlanningSeed) => Harness;

const implementations: Array<[string, MakeHarness]> = [
  [
    'mock',
    (seed) => {
      const store = createMemorySessionStore();
      return {
        services: createMockServices({ store, activities: seed }),
        store,
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
      };
    },
  ],
];

const PLANNING_SEED: ActivityPlanningSeed = {
  activityTypes: [
    {
      id: 'type-planting',
      name: 'Planting',
      category: 'planting',
      standard: true,
    },
    {
      id: 'type-harvest',
      name: 'Harvesting',
      category: 'harvesting',
      standard: true,
    },
  ],
  cycles: [
    { id: 'cycle-1', label: 'North 40 — Wheat 2026' },
    { id: 'cycle-2', label: 'South 12 — Maize 2026' },
  ],
  activities: [
    {
      id: 'activity-1',
      cycleId: 'cycle-1',
      typeId: 'type-planting',
      plannedDate: '2026-03-01',
      status: 'planned',
      resourceNeeds: { inputs: [], labourHours: 0, equipment: '' },
    },
    {
      id: 'activity-2',
      cycleId: 'cycle-2',
      typeId: 'type-harvest',
      plannedDate: '2026-08-01',
      status: 'overdue',
      resourceNeeds: {
        inputs: [{ id: 'need-1', itemName: 'Seed', quantity: 10 }],
        labourHours: 4,
        equipment: 'Tractor',
      },
    },
  ],
};

describe.each(implementations)(
  '%s implementation activity planning conformance',
  (_name, make) => {
    let harness: Harness;

    beforeEach(async () => {
      harness = make(PLANNING_SEED);
      await harness.services.auth.login(VALID);
    });

    it('lists the activity types and filters activities per crop cycle', async () => {
      await expect(harness.services.activityTypes.list()).resolves.toEqual([
        expect.objectContaining({ id: 'type-planting', name: 'Planting' }),
        expect.objectContaining({ id: 'type-harvest', name: 'Harvesting' }),
      ]);

      await expect(harness.services.activities.list()).resolves.toEqual([
        expect.objectContaining({ id: 'activity-1', cycleId: 'cycle-1' }),
        expect.objectContaining({ id: 'activity-2', cycleId: 'cycle-2' }),
      ]);
      await expect(
        harness.services.activities.list('cycle-1'),
      ).resolves.toEqual([
        expect.objectContaining({ id: 'activity-1', cycleId: 'cycle-1' }),
      ]);
      await expect(
        harness.services.activities.list('cycle-9'),
      ).resolves.toEqual([]);
    });

    it('lists crop cycles for the picker, including activity-only cycles', async () => {
      await expect(harness.services.activities.listCycles()).resolves.toEqual([
        { id: 'cycle-1', label: 'North 40 — Wheat 2026' },
        { id: 'cycle-2', label: 'South 12 — Maize 2026' },
      ]);
    });

    it('creates an activity with a type and planned date as planned', async () => {
      const created = await harness.services.activities.create({
        cycleId: 'cycle-1',
        typeId: 'type-harvest',
        plannedDate: '2026-09-01',
      });

      expect(created).toMatchObject({
        id: expect.any(String),
        cycleId: 'cycle-1',
        typeId: 'type-harvest',
        plannedDate: '2026-09-01',
        status: 'planned',
        resourceNeeds: { inputs: [], labourHours: 0, equipment: '' },
      });

      await expect(
        harness.services.activities.list('cycle-1'),
      ).resolves.toEqual([
        expect.objectContaining({ id: 'activity-1' }),
        expect.objectContaining({ id: created.id, status: 'planned' }),
      ]);
    });

    it('rejects a blank planned date and saves nothing', async () => {
      await expect(
        harness.services.activities.create({
          cycleId: 'cycle-1',
          typeId: 'type-planting',
          plannedDate: '   ',
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'plannedDate',
        message: 'Planned date is required.',
      });

      await expect(
        harness.services.activities.list('cycle-1'),
      ).resolves.toHaveLength(1);
    });

    it('requires a known activity type and a crop cycle', async () => {
      await expect(
        harness.services.activities.create({
          cycleId: 'cycle-1',
          typeId: '',
          plannedDate: '2026-05-01',
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'typeId',
        message: 'Select an activity type.',
      });

      await expect(
        harness.services.activities.create({
          cycleId: 'cycle-1',
          typeId: 'type-missing',
          plannedDate: '2026-05-01',
        }),
      ).rejects.toMatchObject({
        status: 404,
        field: 'typeId',
        message: 'The selected activity type does not exist.',
      });

      await expect(
        harness.services.activities.create({
          cycleId: '',
          typeId: 'type-planting',
          plannedDate: '2026-05-01',
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'cycleId',
        message: 'Select a crop cycle.',
      });
    });

    it('saves edited resource needs and re-displays the new values', async () => {
      const updated = await harness.services.activities.updateResourceNeeds(
        'activity-1',
        {
          inputs: [{ itemName: 'Fertilizer', quantity: '25' }],
          labourHours: '12',
          equipment: 'Spreaders',
        },
      );

      expect(updated.resourceNeeds).toEqual({
        inputs: [
          { id: expect.any(String), itemName: 'Fertilizer', quantity: 25 },
        ],
        labourHours: 12,
        equipment: 'Spreaders',
      });

      const [reloaded] = await harness.services.activities.list('cycle-1');
      expect(reloaded?.resourceNeeds).toEqual(updated.resourceNeeds);
    });

    it('rejects malformed resource needs with the offending field', async () => {
      await expect(
        harness.services.activities.updateResourceNeeds('activity-1', {
          inputs: [{ itemName: 'Seed', quantity: '1' }],
          labourHours: '   ',
          equipment: '',
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'labourHours',
        message: 'Labour hours are required.',
      });

      await expect(
        harness.services.activities.updateResourceNeeds('activity-1', {
          inputs: [{ itemName: ' ', quantity: '1' }],
          labourHours: '2',
          equipment: '',
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'inputs',
        message: 'Each input row needs an item name.',
      });

      await expect(
        harness.services.activities.updateResourceNeeds('activity-1', {
          inputs: [{ itemName: 'Seed', quantity: '0' }],
          labourHours: '2',
          equipment: '',
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'inputs',
        message: 'Quantity must be greater than zero.',
      });

      const [unchanged] = await harness.services.activities.list('cycle-1');
      expect(unchanged?.resourceNeeds).toEqual({
        inputs: [],
        labourHours: 0,
        equipment: '',
      });
    });

    it('moves planned to in progress to completed and rejects back-steps', async () => {
      const started = await harness.services.activities.updateStatus(
        'activity-1',
        'in_progress',
      );
      expect(started.status).toBe('in_progress');

      const completed = await harness.services.activities.updateStatus(
        'activity-1',
        'completed',
      );
      expect(completed.status).toBe('completed');

      await expect(
        harness.services.activities.updateStatus('activity-1', 'in_progress'),
      ).rejects.toMatchObject({
        status: 409,
        field: 'status',
        message: 'Cannot move an activity from "completed" to "in_progress".',
      });

      const [reloaded] = await harness.services.activities.list('cycle-1');
      expect(reloaded?.status).toBe('completed');
    });

    it('starts an overdue activity and rejects unknown statuses', async () => {
      const started = await harness.services.activities.updateStatus(
        'activity-2',
        'in_progress',
      );
      expect(started.status).toBe('in_progress');

      await expect(
        harness.services.activities.updateStatus('activity-1', 'paused'),
      ).rejects.toMatchObject({
        status: 400,
        field: 'status',
        message:
          'Status must be one of: planned, in progress, completed, overdue.',
      });
    });

    it('adds a custom activity type and rejects duplicates and blanks', async () => {
      const created = await harness.services.activityTypes.create({
        name: 'Irrigation',
        category: 'custom',
      });

      expect(created).toMatchObject({
        id: expect.any(String),
        name: 'Irrigation',
        category: 'custom',
        standard: false,
      });

      await expect(
        harness.services.activityTypes.create({
          name: 'planting',
          category: 'planting',
        }),
      ).rejects.toMatchObject({
        status: 409,
        field: 'name',
        message: 'A template named "planting" already exists.',
      });

      await expect(
        harness.services.activityTypes.create({
          name: '   ',
          category: 'custom',
        }),
      ).rejects.toMatchObject({
        status: 400,
        field: 'name',
        message: 'Template name is required.',
      });
    });

    it('rejects activity planning requests without a session with 401', async () => {
      const anonymous = make(PLANNING_SEED);

      await expect(anonymous.services.activities.list()).rejects.toMatchObject({
        status: 401,
      });
      await expect(
        anonymous.services.activityTypes.list(),
      ).rejects.toMatchObject({ status: 401 });
      await expect(
        anonymous.services.activities.listCycles(),
      ).rejects.toMatchObject({ status: 401 });
    });
  },
);

describe.each(implementations)(
  '%s implementation activity planning defaults',
  (_name, make) => {
    let harness: Harness;

    beforeEach(async () => {
      harness = make();
      await harness.services.auth.login(VALID);
    });

    it('seeds the five standard activity templates', async () => {
      const types = await harness.services.activityTypes.list();

      expect(types.map((item) => item.name)).toEqual([
        'Land preparation',
        'Planting',
        'Fertilizing',
        'Spraying',
        'Harvesting',
      ]);
      expect(types.every((item) => item.standard)).toBe(true);
    });

    it('seeds demo crop cycles and no activities', async () => {
      await expect(harness.services.activities.listCycles()).resolves.toEqual([
        ...DEFAULT_PLANNING_CYCLES,
      ]);
      await expect(harness.services.activities.list()).resolves.toEqual([]);
    });
  },
);
