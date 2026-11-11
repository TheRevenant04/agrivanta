import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { init, captureException } = vi.hoisted(() => ({
  init: vi.fn(),
  captureException: vi.fn(),
}));

vi.mock('@sentry/react', () => ({ init, captureException }));

describe('error tracking', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv('VITE_SENTRY_DSN', 'https://public@example.ingest.sentry.io/1');
    init.mockClear();
    captureException.mockClear();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('initializes Sentry from the environment DSN and captures errors', async () => {
    const { captureError, initializeErrorTracking } =
      await import('@/lib/telemetry');
    initializeErrorTracking();

    expect(init).toHaveBeenCalledWith({
      dsn: 'https://public@example.ingest.sentry.io/1',
    });

    const error = new Error('synthetic frontend failure');
    captureError(error);
    expect(captureException).toHaveBeenCalledWith(error);
  });
});
