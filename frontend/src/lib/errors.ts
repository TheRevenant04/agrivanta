import { isApiError } from '../services/types';

/** Turns an unknown thrown value into a user-facing message. */
export function toErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    return error.message;
  }

  return 'Something went wrong. Please try again.';
}
