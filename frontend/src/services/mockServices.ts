import type { SessionStore } from './sessionStore';
import { sessionStore as defaultSessionStore } from './sessionStore';
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

  return {
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
  };
}
