import { describe, expect, it, vi } from 'vitest';
import { createHttpServices } from './httpServices';
import { createMemorySessionStore } from './sessionStore';

describe('reporting HTTP transport', () => {
  it('uses authenticated endpoints and preserves binary exports and filters', async () => {
    const store = createMemorySessionStore();
    store.save({
      token: 'test-token',
      user: { id: '1', email: 'test@example.com', role: 'owner' },
    });
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ counts: {}, total: 0 }), { status: 200 }),
      )
      .mockResolvedValueOnce(new Response('file contents', { status: 200 }));
    const reporting = createHttpServices({
      baseUrl: '/api',
      store,
      fetchFn,
    }).reporting;
    await reporting.report('activity-status', { periodId: 'p1' });
    const blob = await reporting.exportReport(
      'activity-status',
      { periodId: 'p1' },
      'xlsx',
    );
    expect(fetchFn).toHaveBeenNthCalledWith(
      1,
      '/api/reports/activity-status?periodId=p1',
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({
          Authorization: 'Bearer test-token',
        }),
      }),
    );
    expect(fetchFn).toHaveBeenNthCalledWith(
      2,
      '/api/reports/activity-status/export?periodId=p1&exportFormat=xlsx',
      expect.anything(),
    );
    expect(blob).toBeInstanceOf(Blob);
  });
});
