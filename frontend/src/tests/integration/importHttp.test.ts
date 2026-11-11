import { describe, expect, it, vi } from 'vitest';
import { createHttpServices } from '@/services/httpServices';
import { createMemorySessionStore } from '@/services/sessionStore';
import type { FetchLike } from '@/services/httpServices';
import type { ImportCommitResult, ImportPreview } from '@/services/types';

const previewResult: ImportPreview = {
  entityType: 'expenses',
  fileName: 'expenses.csv',
  previewToken: 'preview-1',
  expiresAt: '2026-03-01T00:00:00Z',
  totalRows: 0,
  validRows: [],
  invalidRows: [],
  duplicateRows: [],
  counts: { total: 0, valid: 0, invalid: 0, duplicate: 0 },
};

const commitResult: ImportCommitResult = {
  previewToken: 'preview-1',
  entityType: 'expenses',
  imported: [],
  counts: { confirmed: 0, imported: 0, skipped: 0 },
  audit: {
    id: 'audit-1',
    actorId: 'user-1',
    committedAt: '2026-03-01T00:00:00Z',
    entityCounts: { expenses: 0 },
    previewToken: 'preview-1',
  },
};

describe('imports HTTP service', () => {
  it('uses multipart preview and typed JSON commit endpoints', async () => {
    const store = createMemorySessionStore();
    store.save({
      token: 'test-token',
      user: { id: 'user-1', email: 'owner@example.test', role: 'owner' },
    });
    const responses = [
      new Response(JSON.stringify(previewResult), { status: 200 }),
      new Response(JSON.stringify(commitResult), { status: 201 }),
    ];
    const fetchFn = vi.fn<FetchLike>(async () => responses.shift() as Response);
    const services = createHttpServices({
      baseUrl: 'http://localhost:8000/api',
      store,
      fetchFn,
    });
    const file = new File(['date,category,amount'], 'expenses.csv', {
      type: 'text/csv',
    });

    await services.imports.preview('expenses', file);
    await services.imports.commit({
      token: 'preview-1',
      confirmedRows: [{ row: 2, values: { amount: '12.5' } }],
    });

    expect(fetchFn).toHaveBeenCalledTimes(2);
    const [previewUrl, previewInit] = fetchFn.mock.calls[0];
    expect(previewUrl).toBe('http://localhost:8000/api/imports/preview');
    expect(previewInit?.method).toBe('POST');
    expect(previewInit?.body).toBeInstanceOf(FormData);
    expect((previewInit?.body as FormData).get('file')).toBe(file);
    expect((previewInit?.body as FormData).get('entityType')).toBe('expenses');
    expect((previewInit?.headers as Record<string, string>).Authorization).toBe(
      'Bearer test-token',
    );
    expect(previewInit?.headers).not.toHaveProperty('Content-Type');

    const [commitUrl, commitInit] = fetchFn.mock.calls[1];
    expect(commitUrl).toBe('http://localhost:8000/api/imports/commit');
    expect(commitInit?.headers).toHaveProperty(
      'Content-Type',
      'application/json',
    );
    expect(JSON.parse(commitInit?.body as string)).toEqual({
      token: 'preview-1',
      confirmedRows: [{ row: 2, values: { amount: '12.5' } }],
    });
  });
});
