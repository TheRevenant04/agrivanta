import { isApiError } from '../services/types';

/** Turns an unknown thrown value into a user-facing message. */
export function toErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    return error.message;
  }

  return 'Something went wrong. Please try again.';
}

/**
 * Splits an error into the input field it belongs to (so forms can render
 * it inline next to the offending control) and a user-facing message.
 * Returns `field: null` for form-level errors.
 */
export function apiFieldError(error: unknown): {
  field: string | null;
  message: string;
} {
  if (isApiError(error)) {
    return { field: error.field ?? null, message: error.message };
  }

  return { field: null, message: toErrorMessage(error) };
}
