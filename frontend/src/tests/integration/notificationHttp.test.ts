import { describe, expect, it, vi } from 'vitest';
import { createHttpServices } from '@/services/httpServices';
import { createMemorySessionStore } from '@/services/sessionStore';

describe('notification HTTP transport', () => {
  it('loads every page and uses authenticated notification endpoints', async () => {
    const store = createMemorySessionStore();
    store.save({
      token: 'test-token',
      user: { id: '1', email: 'test@example.com', role: 'owner' },
    });
    const first = {
      id: '1',
      type: 'alert',
      message: 'One',
      read: false,
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    };
    const second = { ...first, id: '2', message: 'Two' };
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ nextPage: 2, results: [first] }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ nextPage: null, results: [second] }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ unreadCount: 2 }), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...first, read: true }), { status: 200 }),
      );
    const notifications = createHttpServices({
      baseUrl: '/api',
      store,
      fetchFn,
    }).notifications;

    await expect(notifications.list()).resolves.toEqual([first, second]);
    await expect(notifications.unreadCount()).resolves.toBe(2);
    await expect(notifications.markRead('1')).resolves.toMatchObject({
      id: '1',
      read: true,
    });

    expect(fetchFn).toHaveBeenNthCalledWith(
      1,
      '/api/notifications?page=1&page_size=100',
      expect.objectContaining({ method: 'GET' }),
    );
    expect(fetchFn).toHaveBeenNthCalledWith(
      2,
      '/api/notifications?page=2&page_size=100',
      expect.objectContaining({ method: 'GET' }),
    );
    expect(fetchFn).toHaveBeenNthCalledWith(
      3,
      '/api/notifications/unread-count',
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({
          Authorization: 'Bearer test-token',
        }),
      }),
    );
    expect(fetchFn).toHaveBeenNthCalledWith(
      4,
      '/api/notifications/1/read',
      expect.objectContaining({ method: 'POST' }),
    );
  });
});
