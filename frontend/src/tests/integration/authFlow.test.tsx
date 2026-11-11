import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { App } from '@/App';
import { createMockServices } from '@/services/mockServices';
import {
  SESSION_STORAGE_KEY,
  createSessionStore,
  type SessionStore,
} from '@/services/sessionStore';
import type { AgrivantaServices, AuthSession } from '@/services/types';

const VALID = { email: 'owner@agrivanta.test', password: 'password123' };

function setup(
  options: {
    route?: string;
    store?: SessionStore;
    services?: AgrivantaServices;
  } = {},
) {
  const store = options.store ?? createSessionStore(window.localStorage);
  const services = options.services ?? createMockServices({ store });

  window.history.pushState({}, '', options.route ?? '/login');

  const view = render(<App services={services} store={store} />);
  return { ...view, store, services };
}

function readStoredSession(): AuthSession | null {
  const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
  return raw ? (JSON.parse(raw) as AuthSession) : null;
}

function submitCredentials(email: string, password: string) {
  fireEvent.change(screen.getByLabelText('Email'), {
    target: { value: email },
  });
  fireEvent.change(screen.getByLabelText('Password'), {
    target: { value: password },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
}

describe('auth flow', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.pushState({}, '', '/');
  });

  it('stores the token and navigates to the protected route on valid login', async () => {
    setup({ route: '/login' });

    submitCredentials(VALID.email, VALID.password);

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Dashboard' }),
    ).toBeInTheDocument();
    expect(readStoredSession()?.token).toEqual(expect.any(String));
    expect(readStoredSession()?.user.email).toBe(VALID.email);
  });

  it('shows an accessible inline error and stores no token on invalid login', async () => {
    setup({ route: '/login' });

    submitCredentials(VALID.email, 'wrong-password');

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /invalid email or password/i,
    );
    expect(
      screen.getByRole('heading', { level: 1, name: 'Sign in' }),
    ).toBeInTheDocument();
    expect(readStoredSession()).toBeNull();
  });

  it('registers a new user, stores the token, and lands in the authenticated area', async () => {
    setup({ route: '/register' });

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'New Farmer' },
    });
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'new-farmer@agrivanta.test' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'secret123' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Dashboard' }),
    ).toBeInTheDocument();
    expect(readStoredSession()?.user.email).toBe('new-farmer@agrivanta.test');
  });

  it('clears the stored token and redirects to login on logout', async () => {
    setup({ route: '/login' });
    submitCredentials(VALID.email, VALID.password);

    await screen.findByRole('heading', { level: 1, name: 'Dashboard' });
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Sign in' }),
    ).toBeInTheDocument();
    expect(window.localStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
  });

  it('redirects an unauthenticated visitor from a protected URL to login', async () => {
    setup({ route: '/dashboard' });

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Sign in' }),
    ).toBeInTheDocument();
    expect(readStoredSession()).toBeNull();
  });

  it('keeps an authenticated user on the protected route after a simulated reload', async () => {
    const store = createSessionStore(window.localStorage);
    const services = createMockServices({ store });

    const first = setup({ route: '/login', store, services });
    submitCredentials(VALID.email, VALID.password);
    await screen.findByRole('heading', { level: 1, name: 'Dashboard' });

    first.unmount();

    // Remount with the same storage but brand-new React state.
    window.history.pushState({}, '', '/dashboard');
    render(<App services={services} store={store} />);

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Dashboard' }),
    ).toBeInTheDocument();
    expect(readStoredSession()?.token).toEqual(expect.any(String));
  });

  it('clears a rejected token, redirects to login, and shows a message', async () => {
    const store = createSessionStore(window.localStorage);
    store.save({
      token: 'expired-token',
      user: { id: 'user-owner', email: VALID.email, role: 'owner' },
    });
    const services = createMockServices({ store });

    setup({ route: '/dashboard', store, services });

    expect(await screen.findByRole('status')).toHaveTextContent(
      /session has expired/i,
    );
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Sign in' }),
    ).toBeInTheDocument();
    expect(window.localStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
  });
});
