/**
 * Backend validation rules for the expense and payment domains, mirrored
 * in one place so the mock implementation, the parity fake backend, and
 * the UI forms all agree on messages and status codes.
 *
 * The rules mirror the endpoints described in issues #20, #21, #23 and
 * #24: a blank amount, a blank date, an unknown category, and any edit of
 * a posted expense are rejected with a clear error before anything is
 * persisted.
 */

import { ApiError, type ExpenseCategory } from './types';

/** The categories the backend seeds for expenses (issue #20). */
export const EXPENSE_CATEGORIES: readonly ExpenseCategory[] = [
  'inputs',
  'labour',
  'equipment',
  'overhead',
  'other',
];

export function isExpenseCategory(value: string): value is ExpenseCategory {
  return (EXPENSE_CATEGORIES as readonly string[]).includes(value);
}

/** The payment directions the backend records (issue #23). */
export const PAYMENT_TYPES = ['received', 'paid'] as const;

export function isPaymentType(
  value: string,
): value is (typeof PAYMENT_TYPES)[number] {
  return (PAYMENT_TYPES as readonly string[]).includes(value);
}

/** Single source of truth for expense and payment validation messages. */
export const EXPENSE_PAYMENT_ERRORS = {
  amountRequired: 'Amount is required.',
  amountNotNumeric: 'Amount must be a number.',
  amountInvalid: 'Amount must be a valid number.',
  dateRequired: 'Date is required.',
  categoryRequired: 'Category is required.',
  categoryInvalid:
    'Category must be one of: inputs, labour, equipment, overhead, other.',
  expenseNotFound: 'That expense no longer exists.',
  paymentNotFound: 'That payment no longer exists.',
  postedImmutable: 'Posted expenses cannot be edited or deleted.',
  postedEditRejected: 'Cannot edit a posted expense.',
  postedDeleteRejected: 'Cannot delete a posted expense.',
  attachmentInvalid: 'Invalid attachment.',
} as const;

/**
 * Parses a submitted amount into a number, or throws the backend's error
 * (400, with the offending field) exactly as the API would.
 */
export function parseAmount(value: string | number): number {
  if (typeof value === 'string') {
    const trimmed = value.trim();

    if (trimmed === '') {
      throw new ApiError(EXPENSE_PAYMENT_ERRORS.amountRequired, 400, 'amount');
    }

    const numeric = Number(trimmed);

    if (!Number.isFinite(numeric)) {
      throw new ApiError(
        EXPENSE_PAYMENT_ERRORS.amountNotNumeric,
        400,
        'amount',
      );
    }

    return numeric;
  }

  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      throw new ApiError(
        EXPENSE_PAYMENT_ERRORS.amountNotNumeric,
        400,
        'amount',
      );
    }

    return value;
  }

  throw new ApiError(EXPENSE_PAYMENT_ERRORS.amountRequired, 400, 'amount');
}

/** Parses a transaction date; the backend requires one. */
export function parseExpenseDate(value: string): string {
  const trimmed = (value ?? '').trim();

  if (!trimmed) {
    throw new ApiError(EXPENSE_PAYMENT_ERRORS.dateRequired, 400, 'date');
  }

  return trimmed;
}

/** Checks the category against the backend's seeded list. */
export function requireCategory(value: string): ExpenseCategory {
  if (!value || !isExpenseCategory(value)) {
    throw new ApiError(
      EXPENSE_PAYMENT_ERRORS.categoryInvalid,
      400,
      'category',
    );
  }

  return value;
}

/** Checks the payment direction against the backend's allowed values. */
export function requirePaymentType(value: string): 'received' | 'paid' {
  if (!value || !isPaymentType(value)) {
    throw new ApiError(
      'Payment type must be either received or paid.',
      400,
      'type',
    );
  }

  return value;
}
