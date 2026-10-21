import type {
  Attachment,
  Expense,
  ExpenseInput,
  ExpensePaymentServices,
  Payment,
  PaymentInput,
} from './types';
import type { ServiceRequest } from './farmSetupHttp';

/**
 * Multipart upload helper the HTTP services layer exposes. It posts a
 * `FormData` body (no JSON content type) and maps the response exactly
 * like {@link ServiceRequest} does.
 */
export type UploadRequest = <T>(
  path: string,
  file: File,
  authenticated: boolean,
) => Promise<T>;

function body(input: unknown): RequestInit {
  return { method: 'POST', body: JSON.stringify(input) };
}

function put(input: unknown): RequestInit {
  return { method: 'PUT', body: JSON.stringify(input) };
}

/**
 * HTTP implementation of the expense and payment domains.
 *
 * Routes mirror the backend tasks #20, #23 and #24:
 * - `GET/POST /expenses`
 * - `PUT/DELETE /expenses/:id`
 * - `POST /expenses/:id/post` (draft -> posted)
 * - `POST /expenses/:id/attachments` (multipart receipt upload)
 * - `GET/POST /payments`
 */
export function createExpensePaymentHttp(
  request: ServiceRequest,
  upload: UploadRequest,
): ExpensePaymentServices {
  return {
    expenses: {
      list: () => request<Expense[]>('/expenses', { method: 'GET' }, true),
      create: (input: ExpenseInput) =>
        request<Expense>('/expenses', body(input), true),
      update: (id: string, input: ExpenseInput) =>
        request<Expense>(
          `/expenses/${encodeURIComponent(id)}`,
          put(input),
          true,
        ),
      remove: (id: string) =>
        request<void>(
          `/expenses/${encodeURIComponent(id)}`,
          { method: 'DELETE' },
          true,
        ),
      post: (id: string) =>
        request<Expense>(
          `/expenses/${encodeURIComponent(id)}/post`,
          { method: 'POST' },
          true,
        ),
      uploadAttachment: (expenseId: string, file: File) =>
        upload<Attachment>(
          `/expenses/${encodeURIComponent(expenseId)}/attachments`,
          file,
          true,
        ),
    },
    payments: {
      list: () => request<Payment[]>('/payments', { method: 'GET' }, true),
      create: (input: PaymentInput) =>
        request<Payment>('/payments', body(input), true),
    },
  };
}
