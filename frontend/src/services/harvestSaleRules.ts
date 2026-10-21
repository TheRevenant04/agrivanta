/**
 * Backend validation rules for the harvest and sale domains, mirrored in one
 * place so the mock implementation, the parity fake backend, and the UI forms
 * all agree on messages, status codes, and offending fields.
 *
 * They mirror the endpoints described in issues #28 (harvest records) and #29
 * (sales and revenue records): a harvest needs an open crop cycle, a positive
 * quantity, a unit, and a valid date; a sale needs a customer, a harvest, a
 * positive quantity, a positive unit price, and a valid date; and a sale can
 * never sell more than the harvest's remaining unsold quantity.
 */

import { ApiError } from './types';
import type { ConversionQuery, ConversionResult, Harvest } from './types';

/** Messages shared by both record types. */
export const RECORD_ERRORS = {
  dateRequired: 'Date is required.',
  dateInvalid: 'Date must be a valid calendar date.',
} as const;

/** Single source of truth for harvest validation messages. */
export const HARVEST_ERRORS = {
  cycleRequired: 'Select a crop cycle.',
  cycleNotFound: 'That crop cycle no longer exists.',
  cycleClosed: 'This crop cycle is closed and can no longer be harvested.',

  quantityRequired: 'Quantity is required.',
  quantityNotNumeric: 'Quantity must be a number.',
  quantityNotPositive: 'Quantity must be greater than zero.',

  unitRequired: 'Select a unit.',
} as const;

/** Single source of truth for sale validation messages. */
export const SALE_ERRORS = {
  customerRequired: 'Select a customer.',
  customerNotFound: 'That customer does not exist.',

  harvestRequired: 'Select a harvest.',
  harvestNotFound: 'That harvest no longer exists.',

  quantityRequired: 'Quantity is required.',
  quantityNotNumeric: 'Quantity must be a number.',
  quantityNotPositive: 'Quantity must be greater than zero.',

  unitPriceRequired: 'Unit price is required.',
  unitPriceNotNumeric: 'Unit price must be a number.',
  unitPriceNotPositive: 'Unit price must be greater than zero.',

  soldExceedsHarvested: (available: number) =>
    `Sold quantity exceeds the harvested quantity available. Maximum sellable is ${formatAmount(available)}.`,
} as const;

/** Rounds an amount for display and comparison, avoiding float noise. */
export function formatAmount(value: number): string {
  return String(Math.round(value * 10000) / 10000);
}

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

/** Parses a required ISO date, or throws the backend's 400 rule. */
export function parseRecordDate(value: string): string {
  const trimmed = value.trim();

  if (!trimmed) {
    throw new ApiError(RECORD_ERRORS.dateRequired, 400, 'date');
  }

  if (!isIsoCalendarDate(trimmed)) {
    throw new ApiError(RECORD_ERRORS.dateInvalid, 400, 'date');
  }

  return trimmed;
}

function parseRequiredNumber(
  value: string | number,
  field: string,
  requiredMessage: string,
  notNumericMessage: string,
): number {
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      throw new ApiError(notNumericMessage, 400, field);
    }

    return value;
  }

  const trimmed = value.trim();

  if (trimmed === '') {
    throw new ApiError(requiredMessage, 400, field);
  }

  const numeric = Number(trimmed);

  if (!Number.isFinite(numeric)) {
    throw new ApiError(notNumericMessage, 400, field);
  }

  return numeric;
}

/** Parses a harvest quantity; blank, non-numeric, zero, and negative fail. */
export function parseHarvestQuantity(value: string | number): number {
  const numeric = parseRequiredNumber(
    value,
    'quantity',
    HARVEST_ERRORS.quantityRequired,
    HARVEST_ERRORS.quantityNotNumeric,
  );

  if (numeric <= 0) {
    throw new ApiError(HARVEST_ERRORS.quantityNotPositive, 400, 'quantity');
  }

  return numeric;
}

/** Parses a sale quantity; blank, non-numeric, zero, and negative fail. */
export function parseSaleQuantity(value: string | number): number {
  const numeric = parseRequiredNumber(
    value,
    'quantity',
    SALE_ERRORS.quantityRequired,
    SALE_ERRORS.quantityNotNumeric,
  );

  if (numeric <= 0) {
    throw new ApiError(SALE_ERRORS.quantityNotPositive, 400, 'quantity');
  }

  return numeric;
}

/** Parses a unit price; blank, non-numeric, zero, and negative fail. */
export function parseUnitPrice(value: string | number): number {
  const numeric = parseRequiredNumber(
    value,
    'unitPrice',
    SALE_ERRORS.unitPriceRequired,
    SALE_ERRORS.unitPriceNotNumeric,
  );

  if (numeric <= 0) {
    throw new ApiError(SALE_ERRORS.unitPriceNotPositive, 400, 'unitPrice');
  }

  return numeric;
}

export interface HarvestedTotal {
  total: number;
  /** The unit the total is expressed in; null when there are no harvests. */
  unitId: string | null;
}

/**
 * Sums a cycle's harvests in the unit of its first harvest, converting the
 * other entries through the backend's unit-conversion rule (issue #28 applies
 * conversions before aggregating). Rejects with the conversion domain's
 * "no rule exists" error, naming the units, when a conversion is missing.
 */
export async function computeHarvestedTotal(
  harvests: Harvest[],
  convert: (query: ConversionQuery) => Promise<ConversionResult>,
): Promise<HarvestedTotal> {
  if (harvests.length === 0) {
    return { total: 0, unitId: null };
  }

  const unitId = harvests[0].unitId;
  let total = 0;

  for (const harvest of harvests) {
    if (harvest.unitId === unitId) {
      total += harvest.quantity;
      continue;
    }

    const converted = await convert({
      fromUnitId: harvest.unitId,
      toUnitId: unitId,
      quantity: harvest.quantity,
    });
    total += converted.converted;
  }

  return { total: Math.round(total * 10000) / 10000, unitId };
}
