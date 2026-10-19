import { beforeEach, describe, expect, it } from 'vitest';
import {
  SESSION_STORAGE_KEY,
  createMemorySessionStore,
  createSessionStore,
} from './sessionStore';
import type { AuthSession } from './types';

const session: AuthSession = {
  token: 'token-1',
  user: { id: 'user-1', email: 'owner@agrivanta.test', role: 'owner' },
};

describe('session store', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('persists the token in localStorage and restores it after a reload', () => {
    const store = createSessionStore(window.localStorage);
    store.save(session);

    expect(window.localStorage.getItem(SESSION_STORAGE_KEY)).toContain(
      'token-1',
    );

    // A fresh store represents the next page load reading the same storage.
    const reloaded = createSessionStore(window.localStorage);
    expect(reloaded.get()).toEqual(session);
    expect(reloaded.getToken()).toBe('token-1');
  });

  it('clears the stored token', () => {
    const store = createSessionStore(window.localStorage);
    store.save(session);
    store.clear();

    expect(store.get()).toBeNull();
    expect(store.getToken()).toBeNull();
    expect(window.localStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
  });

  it('treats malformed payloads as no session', () => {
    window.localStorage.setItem(SESSION_STORAGE_KEY, '{not-json');
    expect(createSessionStore(window.localStorage).get()).toBeNull();
  });

  it('provides an in-memory store with the same behaviour', () => {
    const store = createMemorySessionStore();
    expect(store.get()).toBeNull();

    store.save(session);
    expect(store.get()).toEqual(session);
    expect(store.getToken()).toBe('token-1');

    store.clear();
    expect(store.get()).toBeNull();
  });
});
