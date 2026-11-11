import { beforeEach, describe, expect, it } from 'vitest';
import { MOCK_USERS, createMockServices } from '@/services/mockServices';
import { createMemorySessionStore } from '@/services/sessionStore';
import type { AgrivantaServices, AuthSession } from '@/services/types';

const VALID = { email: 'owner@agrivanta.test', password: 'password123' };

describe('mock services', () => {
  let store = createMemorySessionStore();
  let services: AgrivantaServices = createMockServices({ store });

  beforeEach(() => {
    store = createMemorySessionStore();
    services = createMockServices({ store });
  });

  it('logs in with valid credentials, stores the token, and returns a typed session', async () => {
    const session: AuthSession = await services.auth.login(VALID);

    expect(session).toEqual({
      token: expect.any(String),
      user: {
        id: 'user-owner',
        email: 'owner@agrivanta.test',
        role: 'owner',
      },
    });
    expect(store.getToken()).toBe(session.token);
    await expect(services.auth.me()).resolves.toEqual(session.user);
  });

  it('rejects invalid credentials without storing a token', async () => {
    await expect(
      services.auth.login({ email: VALID.email, password: 'wrong-password' }),
    ).rejects.toMatchObject({ status: 401, name: 'InvalidCredentialsError' });

    expect(store.getToken()).toBeNull();
    expect(store.get()).toBeNull();
  });

  it('clears the token on logout and rejects me() afterwards', async () => {
    await services.auth.login(VALID);
    expect(store.getToken()).not.toBeNull();

    await services.auth.logout();

    expect(store.getToken()).toBeNull();
    await expect(services.auth.me()).rejects.toMatchObject({ status: 401 });
  });

  it('registers a new user, stores the token, and allows a later login', async () => {
    const input = {
      name: 'New Farmer',
      email: 'new-farmer@agrivanta.test',
      password: 'secret123',
    };

    const session = await services.auth.register(input);

    expect(session.token).toEqual(expect.any(String));
    expect(session.user).toEqual({
      id: expect.any(String),
      email: input.email,
      role: 'owner',
    });
    expect(store.getToken()).toBe(session.token);
    await expect(services.auth.me()).resolves.toEqual(session.user);

    await expect(
      services.auth.login({ email: input.email, password: input.password }),
    ).resolves.toMatchObject({ user: { email: input.email } });
  });

  it('rejects a duplicate registration', async () => {
    await expect(
      services.auth.register({ email: VALID.email, password: 'anything' }),
    ).rejects.toMatchObject({ status: 409 });
  });

  it('ships seed credentials for local development', () => {
    expect(MOCK_USERS.map((user) => user.email)).toContain(VALID.email);
  });
});
