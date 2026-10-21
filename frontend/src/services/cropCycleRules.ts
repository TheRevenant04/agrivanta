/**
 * Backend validation rules for the crop cycle domain, mirrored in one
 * place so the mock implementation, the parity fake backend, and the UI
 * forms all agree on messages and status codes.
 *
 * The rules mirror the endpoints the crop cycle screens call (the backend
 * lands with issue #11): a cycle requires a field, crop, variety, and
 * start date; the optional end date cannot precede the start date;
 * expected yield and price must be non-negative numbers; and a closed
 * cycle is locked against further edits (`_docs/plan.md` §3.1). Overlapping
 * cycles on the same field are deliberately allowed.
 */

import { ApiError } from './types';

/** Single source of truth for crop cycle validation messages. */
export const CYCLE_ERRORS = {
  cycleFieldRequired: 'Select a field for this crop cycle.',
  cycleCropRequired: 'Select a crop for this crop cycle.',
  cycleVarietyRequired: 'Select a variety for this crop cycle.',

  startDateRequired: 'Start date is required.',
  startDateInvalid: 'Start date must be a valid calendar date.',
  endDateInvalid: 'End date must be a valid calendar date.',
  endDateBeforeStart: 'End date cannot be before the start date.',

  yieldNotNumeric: 'Expected yield must be a number.',
  yieldNegative: 'Expected yield cannot be negative.',
  priceNotNumeric: 'Expected price must be a number.',
  priceNegative: 'Expected price cannot be negative.',

  cycleNotFound: 'That crop cycle no longer exists.',
  cycleClosed: 'This crop cycle is closed and can no longer be edited.',
  cycleAlreadyClosed: 'This crop cycle is already closed.',
} as const;

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

/** True when `value` is an ISO date that exists on the calendar. */
export function isIsoCalendarDate(value: string): boolean {
  if (!ISO_DATE_PATTERN.test(value)) {
    return false;
  }

  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));

  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

/** Parses the required start date, or throws the backend's 400 rule. */
export function parseStartDate(value: string): string {
  const trimmed = value.trim();

  if (!trimmed) {
    throw new ApiError(CYCLE_ERRORS.startDateRequired, 400, 'startDate');
  }

  if (!isIsoCalendarDate(trimmed)) {
    throw new ApiError(CYCLE_ERRORS.startDateInvalid, 400, 'startDate');
  }

  return trimmed;
}

/**
 * Parses the optional end date; a blank value means "no end date
 * recorded". Rejects dates before the start date, mirroring the backend.
 */
export function parseEndDate(
  value: string,
  startDate: string,
): string | undefined {
  const trimmed = value.trim();

  if (!trimmed) {
    return undefined;
  }

  if (!isIsoCalendarDate(trimmed)) {
    throw new ApiError(CYCLE_ERRORS.endDateInvalid, 400, 'endDate');
  }

  // ISO dates sort chronologically as plain strings.
  if (trimmed < startDate) {
    throw new ApiError(CYCLE_ERRORS.endDateBeforeStart, 400, 'endDate');
  }

  return trimmed;
}

/** The two optional money/quantity fields a cycle can carry. */
export type CycleAmountField = 'expectedYield' | 'expectedPrice';

/**
 * Parses an optional expected yield or price. A blank value clears the
 * stored amount; a non-numeric or negative value raises the backend's
 * 400 rule with the offending field.
 */
export function parseOptionalAmount(
  value: string | number | undefined,
  field: CycleAmountField,
): number | undefined {
  let numeric: number;

  if (value === undefined) {
    return undefined;
  }

  if (typeof value === 'number') {
    numeric = value;
  } else {
    const trimmed = value.trim();

    if (trimmed === '') {
      return undefined;
    }

    numeric = Number(trimmed);
  }

  if (!Number.isFinite(numeric)) {
    throw new ApiError(
      field === 'expectedYield'
        ? CYCLE_ERRORS.yieldNotNumeric
        : CYCLE_ERRORS.priceNotNumeric,
      400,
      field,
    );
  }

  if (numeric < 0) {
    throw new ApiError(
      field === 'expectedYield'
        ? CYCLE_ERRORS.yieldNegative
        : CYCLE_ERRORS.priceNegative,
      400,
      field,
    );
  }

  return numeric;
}
