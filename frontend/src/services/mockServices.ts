import type { SessionStore } from './sessionStore';
import { sessionStore as defaultSessionStore } from './sessionStore';
import { createFarmSetupMock, type FarmSetupSeed } from './farmSetupMock';
import { createHarvestSaleMock, type HarvestSaleSeed } from './harvestSaleMock';
import { createInventoryMock, type InventorySeed } from './inventoryMock';
// Crop cycle domain (issue #45).
import { createCropCycleMock } from './cropCycleMock';
import {
  createActivityPlanningMock,
  type ActivityPlanningSeed,
} from './activityPlanningMock';
import {
  createExpensePaymentMock,
  type ExpensePaymentSeed,
} from './expensePaymentMock';
import {
  ApiError,
  InvalidCredentialsError,
  UnauthorizedError,
  type AgrivantaServices,
  type AuthSession,
  type CropCycle,
  type LoginCredentials,
  type RegisterInput,
  type User,
} from './types';

interface SeedUser extends User {
  password: string;
  name?: string;
}

export const MOCK_USERS: readonly SeedUser[] = [
  {
    id: 'user-owner',
    email: 'owner@agrivanta.test',
    password: 'password123',
    role: 'owner',
    name: 'Olive Owner',
  },
  {
    id: 'user-manager',
    email: 'manager@agrivanta.test',
    password: 'password123',
    role: 'manager',
    name: 'Manny Manager',
  },
];

const TOKEN_PREFIX = 'mock.';

function publicUser(user: SeedUser): User {
  return { id: user.id, email: user.email, role: user.role };
}

/**
 * The token encodes the user so the mock can resolve `me()` after a page
 * refresh without keeping server-like state in memory.
 */
function encodeToken(user: User): string {
  return `${TOKEN_PREFIX}${btoa(JSON.stringify(user))}`;
}

function decodeToken(token: string): User | null {
  if (!token.startsWith(TOKEN_PREFIX)) {
    return null;
  }

  try {
    const parsed: unknown = JSON.parse(atob(token.slice(TOKEN_PREFIX.length)));

    if (
      typeof parsed === 'object' &&
      parsed !== null &&
      typeof (parsed as { id?: unknown }).id === 'string' &&
      typeof (parsed as { email?: unknown }).email === 'string' &&
      typeof (parsed as { role?: unknown }).role === 'string'
    ) {
      return parsed as User;
    }
  } catch {
    // Fall through to "invalid token".
  }

  return null;
}

export interface MockServicesOptions {
  store?: SessionStore;
  users?: readonly SeedUser[];
  /** Seed for the farm, field, crop, variety, unit, and conversion domains. */
  farmSetup?: FarmSetupSeed;
  /** Seed for the harvest, sale, and sale-customer domains (issue #49). */
  harvestSale?: HarvestSaleSeed;
  /** Seed for expenses and payments. */
  expensePayments?: ExpensePaymentSeed;
  /** Seed for the inventory domain (issue #47): items and movements. */
  inventory?: InventorySeed;
  /** Seed for the activity type, cycle, and activity domains (issue #46). */
  activities?: ActivityPlanningSeed;
  /** Seed crop cycles for the crop cycle domain (issue #45). */
  cropCycles?: CropCycle[];
}

/**
 * In-memory implementation of {@link AgrivantaServices}. It needs no server,
 * so the app boots and the whole auth flow works with the default config.
 */
export function createMockServices(
  options: MockServicesOptions = {},
): AgrivantaServices {
  const store = options.store ?? defaultSessionStore;
  const users: SeedUser[] = (options.users ?? MOCK_USERS).map((user) => ({
    ...user,
  }));
  let sequence = users.length;

  const normalizeEmail = (email: string) => email.trim().toLowerCase();

  const findByEmail = (email: string) =>
    users.find((user) => normalizeEmail(user.email) === normalizeEmail(email));

  const sessionFor = (user: SeedUser): AuthSession => {
    const publicProfile = publicUser(user);
    return { token: encodeToken(publicProfile), user: publicProfile };
  };

  const requireUser = (): User => {
    const token = store.getToken();

    if (!token) {
      throw new UnauthorizedError();
    }

    const user = decodeToken(token);

    if (!user) {
      throw new UnauthorizedError();
    }

    return user;
  };

  const farmSetup = createFarmSetupMock({
    seed: options.farmSetup,
    requireAuth: requireUser,
  });

  return {
    reporting: {
      async periods() {
        requireUser();
        return [];
      },
      async seasons() {
        requireUser();
        return [];
      },
      async dashboard() {
        requireUser();
        return {
          currentCycleSpend: 0,
          revenueToDate: 0,
          unsoldProduce: [],
          upcomingActivities: 0,
          overdueActivities: 0,
          lowStockItemCount: 0,
        };
      },
      async report(name) {
        requireUser();
        if (name === 'activity-status')
          return {
            counts: { planned: 0, in_progress: 0, completed: 0, overdue: 0 },
            total: 0,
          };
        if (name === 'inventory')
          return { asOf: new Date().toISOString().slice(0, 10), items: [] };
        if (name === 'budget-vs-actual') return { overall: [], categories: [] };
        return { groupBy: 'cycle', rows: [], totals: { hours: 0, cost: 0 } };
      },
      async exportReport() {
        requireUser();
        throw new ApiError('Report exports require the HTTP API.', 501);
      },
    },
    auth: {
      async login(credentials: LoginCredentials) {
        const user = findByEmail(credentials.email);

        if (!user || user.password !== credentials.password) {
          throw new InvalidCredentialsError();
        }

        const session = sessionFor(user);
        store.save(session);
        return session;
      },

      async register(input: RegisterInput) {
        if (!input.email.trim() || !input.password) {
          throw new ApiError('Email and password are required.', 422);
        }

        if (findByEmail(input.email)) {
          throw new ApiError('An account with that email already exists.', 409);
        }

        sequence += 1;
        const user: SeedUser = {
          id: `user-${sequence}`,
          email: input.email.trim(),
          password: input.password,
          role: 'owner',
          name: input.name,
        };
        users.push(user);

        const session = sessionFor(user);
        store.save(session);
        return session;
      },

      async logout() {
        store.clear();
      },

      async me() {
        return requireUser();
      },
    },

    // Farm setup domains (issue #44) share the same session requirement.
    ...farmSetup,

    // Inventory domain (issue #47) mirrors backend issue #16, resolving
    // units through the farm setup mock so both stay in sync.
    ...createInventoryMock({
      seed: options.inventory,
      requireAuth: requireUser,
      findUnit: async (id) =>
        (await farmSetup.units.list()).find((unit) => unit.id === id) ?? null,
    }),

    // Activity planning domains (issue #46) share the session requirement.
    ...createActivityPlanningMock({
      seed: options.activities,
      requireAuth: requireUser,
    }),

    // Crop cycle domain (issue #45) shares the same session requirement.
    ...createCropCycleMock({
      seed: options.cropCycles,
      requireAuth: requireUser,
    }),

    // Expense and payment domains (issue #49)
    ...createExpensePaymentMock({
      seed: options.expensePayments,
      requireAuth: requireUser,
    }),

    imports: {
      async preview() {
        requireUser();
        throw new ApiError('File imports require the HTTP API client.', 501);
      },
      async commit() {
        requireUser();
        throw new ApiError('File imports require the HTTP API client.', 501);
      },
    },

    // Harvest and sale domains (issue #49) are session-protected too.
    ...createHarvestSaleMock({
      seed: options.harvestSale,
      requireAuth: requireUser,
    }),
  };
}
