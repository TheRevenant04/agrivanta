import * as Sentry from '@sentry/react';

export function initializeErrorTracking(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) return;

  Sentry.init({
    dsn,
  });
}

export function captureError(error: unknown): void {
  Sentry.captureException(error);
}
