import { beforeEach, describe, expect, it } from 'vitest';
import { createExpensePaymentMock } from './expensePaymentMock';
import { createHttpServices } from './httpServices';
import { createMockServices } from './mockServices';
import { createMemorySessionStore } from './sessionStore';
import {
  ApiError,
  isApiError,
  type AgrivantaServices,
  type ExpenseInput,
  type PaymentInput,
} from './types';

const BASE_URL = 'https://api.agrivanta.test/v1';
const VALID = { email: 'owner@agrivanta.test', password: 'password123' };

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function readTokenHeader(init: RequestInit | undefined): string | null {
  const headers = init?.headers as Record<string, string> | undefined;
  const header = headers?.Authorization;
  return header ? header.replace(/^Bearer\s+/, '') : null;
}

/**
 * Minimal in-memory stand-in for the backend so the HTTP implementation can
 * be exercised with the same expectations as the mock. The expense and
 * payment endpoints delegate to the shared mock engine (with auth enforced
 * here at the HTTP boundary) so both implementations are held to one rule
 * set, exactly like the farm setup parity tests do.
 */
function createFakeBackend() {
  const users = new Map<
    string,
    { password: string; user: { id: string; email: string; role: string } }
  >();
  users.set(VALID.email, {
    password: VALID.password,
    user: { id: 'user-owner', email: VALID.email, role: 'owner' },
  });
  const sessions = new Map<string, { id: string; email: string; role: string }>();
  const engine = createExpensePaymentMock({ requireAuth: () => undefined });

  /** Maps a services-layer error onto the backend's error envelope. */
  function fail(error: unknown): Response {
    if (isApiError(error)) {
      const apiError = error as ApiError;
      return json(
        { detail: apiError.message, field: apiError.field },
        apiError.status,
      );
    }
    return json({ detail: 'Something went wrong.' }, 500);
  }

  const fetchFn = async (
    input: string,
    init: RequestInit = {},
  ): Promise<Response> => {
    const path = new URL(String(input)).pathname;
    const method = init.method ?? 'GET';

    if (method === 'POST' && path.endsWith('/auth/login')) {
      const body = JSON.parse(String(init.body)) as {
        email: string;
        password: string;
      };
      const record = users.get(body.email);

      if (!record || record.password !== body.password) {
        return json({ detail: 'Invalid credentials' }, 401);
      }

      const token = `token-${record.user.id}`;
      sessions.set(token, record.user);
      return json({ token, user: record.user });
    }

    if (method === 'GET' && path.endsWith('/auth/me')) {
      const token = readTokenHeader(init);
      const user = token ? sessions.get(token) : undefined;

      if (!user) {
        return json({ detail: 'Unauthorized' }, 401);
      }

      return json(user);
    }

    const token = readTokenHeader(init);

    if (!token || !sessions.has(token)) {
      return json({ detail: 'Unauthorized' }, 401);
    }

    const parsePayload = (): unknown =>
      init.body ? JSON.parse(String(init.body)) : {};

    try {
      if (path.endsWith('/expenses') && method === 'GET') {
        return json(await engine.expenses.list());
      }

      if (path.endsWith('/expenses') && method === 'POST') {
        return json(
          await engine.expenses.create(parsePayload() as ExpenseInput),
          201,
        );
      }

      const attachmentMatch = /\/expenses\/([^/]+)\/attachments$/.exec(path);

      if (attachmentMatch && method === 'POST') {
        const form = init.body as FormData;
        const file = form.get('file') as File | null;

        if (!file) {
          return json({ detail: 'Invalid attachment.' }, 400);
        }

        return json(
          await engine.expenses.uploadAttachment(attachmentMatch[1], file),
          201,
        );
      }

      const postMatch = /\/expenses\/([^/]+)\/post$/.exec(path);

      if (postMatch && method === 'POST') {
        return json(await engine.expenses.post(postMatch[1]));
      }

      const expenseMatch = /\/expenses\/([^/]+)$/.exec(path);

      if (expenseMatch) {
        const id = expenseMatch[1];

        if (method === 'PUT') {
          return json(
            await engine.expenses.update(id, parsePayload() as ExpenseInput),
          );
        }

        if (method === 'DELETE') {
          await engine.expenses.remove(id);
          return new Response(null, { status: 204 });
        }
      }

      if (path.endsWith('/payments') && method === 'GET') {
        return json(await engine.payments.list());
      }

      if (path.endsWith('/payments') && method === 'POST') {
        return json(
          await engine.payments.create(parsePayload() as PaymentInput),
          201,
        );
      }
    } catch (error) {
      return fail(error);
    }

    return json({ detail: 'Not found' }, 404);
  };

  return { fetchFn };
}

function makeMockServices(): AgrivantaServices {
  return createMockServices({ store: createMemorySessionStore() });
}

function makeHttpServices(): AgrivantaServices {
  const backend = createFakeBackend();
  return createHttpServices({
    baseUrl: BASE_URL,
    store: createMemorySessionStore(),
    fetchFn: backend.fetchFn,
  });
}

const IMPLEMENTATIONS: Array<[string, () => AgrivantaServices]> = [
  ['mock', makeMockServices],
  ['http', makeHttpServices],
];

describe('expense and payment parity between mock and http', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  for (const [kind, factory] of IMPLEMENTATIONS) {
    it(`${kind}: creates a draft expense and lists it`, async () => {
      const services = factory();
      await services.auth.login(VALID);

      const created = await services.expenses.create({
        category: 'inputs',
        amount: '10.50',
        date: '2026-01-01',
        supplier: 'Acme',
      });

      expect(created.status).toBe('draft');
      expect(created.amount).toBe(10.5);
      expect(created.supplier).toBe('Acme');

      const list = await services.expenses.list();
      expect(list).toHaveLength(1);
    });

    it(`${kind}: posting flips the status to posted`, async () => {
      const services = factory();
      await services.auth.login(VALID);

      const created = await services.expenses.create({
        category: 'labour',
        amount: 20,
        date: '2026-01-02',
      });
      const posted = await services.expenses.post(created.id);

      expect(posted.status).toBe('posted');
    });

    it(`${kind}: rejects editing a posted expense`, async () => {
      const services = factory();
      await services.auth.login(VALID);

      const created = await services.expenses.create({
        category: 'equipment',
        amount: 100,
        date: '2026-01-03',
      });
      await services.expenses.post(created.id);

      await expect(
        services.expenses.update(created.id, {
          category: 'equipment',
          amount: 120,
          date: '2026-01-03',
        }),
      ).rejects.toMatchObject({ status: 400 });
    });

    it(`${kind}: rejects deleting a posted expense`, async () => {
      const services = factory();
      await services.auth.login(VALID);

      const created = await services.expenses.create({
        category: 'overhead',
        amount: 50,
        date: '2026-01-04',
      });
      await services.expenses.post(created.id);

      await expect(services.expenses.remove(created.id)).rejects.toMatchObject({
        status: 400,
      });
    });

    it(`${kind}: reports the offending field when the amount is missing`, async () => {
      const services = factory();
      await services.auth.login(VALID);

      const failure = await services.expenses
        .create({ category: 'inputs', amount: '', date: '2026-01-05' })
        .then(
          () => null,
          (error: unknown) => error,
        );

      expect(failure).toBeInstanceOf(ApiError);
      expect(isApiError(failure)).toBe(true);
      expect((failure as ApiError).status).toBe(400);
      expect((failure as ApiError).field).toBe('amount');

      const list = await services.expenses.list();
      expect(list).toHaveLength(0);
    });

    it(`${kind}: reports the offending field when the date is missing`, async () => {
      const services = factory();
      await services.auth.login(VALID);

      const failure = await services.expenses
        .create({ category: 'inputs', amount: 5, date: '' })
        .then(
          () => null,
          (error: unknown) => error,
        );

      expect((failure as ApiError).field).toBe('date');
      expect(await services.expenses.list()).toHaveLength(0);
    });

    it(`${kind}: reports the offending field for an unknown category`, async () => {
      const services = factory();
      await services.auth.login(VALID);

      const failure = await services.expenses
        .create({
          category: 'nonsense' as never,
          amount: 5,
          date: '2026-01-05',
        })
        .then(
          () => null,
          (error: unknown) => error,
        );

      expect((failure as ApiError).field).toBe('category');
      expect(await services.expenses.list()).toHaveLength(0);
    });

    it(`${kind}: uploads a receipt attachment and keeps its file name`, async () => {
      const services = factory();
      await services.auth.login(VALID);

      const created = await services.expenses.create({
        category: 'other',
        amount: 15,
        date: '2026-01-06',
      });
      const file = new File(['receipt'], 'receipt.pdf', {
        type: 'application/pdf',
      });
      const attachment = await services.expenses.uploadAttachment(
        created.id,
        file,
      );

      expect(attachment.name).toBe('receipt.pdf');

      const list = await services.expenses.list();
      expect(list[0].attachments?.[0]?.name).toBe('receipt.pdf');
    });

    it(`${kind}: saves a payment and lists it`, async () => {
      const services = factory();
      await services.auth.login(VALID);

      const payment = await services.payments.create({
        type: 'paid',
        amount: 25,
        date: '2026-02-01',
        linkedExpenseId: 'expense-1',
      });

      expect(payment.type).toBe('paid');
      expect(payment.linkedExpenseId).toBe('expense-1');

      const list = await services.payments.list();
      expect(list).toHaveLength(1);
    });

    it(`${kind}: reports the offending field when a payment is missing its amount`, async () => {
      const services = factory();
      await services.auth.login(VALID);

      const failure = await services.payments
        .create({ type: 'received', amount: '', date: '2026-02-02' })
        .then(
          () => null,
          (error: unknown) => error,
        );

      expect((failure as ApiError).field).toBe('amount');
      expect(await services.payments.list()).toHaveLength(0);
    });
  }
});
