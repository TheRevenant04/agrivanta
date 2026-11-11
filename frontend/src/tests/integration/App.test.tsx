import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '@/App';
import { SESSION_STORAGE_KEY } from '@/services/sessionStore';

describe('App (default mock mode)', () => {
  const fetchSpy = vi.fn(() =>
    Promise.reject(new Error('fetch must not be called in mock mode')),
  );

  beforeEach(() => {
    window.localStorage.clear();
    window.history.pushState({}, '', '/');
    fetchSpy.mockClear();
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('boots and renders the login page with no backend running', async () => {
    render(<App />);

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Sign in' }),
    ).toBeInTheDocument();
    expect(window.localStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
