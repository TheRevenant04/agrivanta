/**
 * Backend validation rules for the farm setup domains, mirrored in one
 * place so the mock implementation, the parity fake backend, and the UI
 * forms all agree on messages and status codes.
 *
 * The rules mirror the endpoints described in issues #8, #9, and #10:
 * a blank field name, a non-numeric or negative area, a missing base
 * measure category, and a conversion with no matching rule are all
 * rejected with a clear error before anything is persisted.
 */

import { ApiError, type BaseMeasureCategory } from '@/services/types';

export const BASE_MEASURE_CATEGORIES: readonly BaseMeasureCategory[] = [
  'mass',
  'volume',
  'count',
];

export function isBaseMeasureCategory(
  value: string,
): value is BaseMeasureCategory {
  return (BASE_MEASURE_CATEGORIES as readonly string[]).includes(value);
}

/** The reporting currency must be a three-letter code such as `USD`. */
export function isValidReportingCurrency(value: string): boolean {
  return /^[A-Za-z]{3}$/.test(value.trim());
}

/** Single source of truth for farm setup validation messages. */
export const SETUP_ERRORS = {
  farmNameRequired: 'Farm name is required.',
  currencyInvalid:
    'Reporting currency must be a three-letter code such as USD.',
  farmNotFound: 'No farm is configured.',

  fieldNameRequired: 'Field name is required.',
  areaNotNumeric: 'Area must be a number.',
  areaNegative: 'Area cannot be negative.',
  fieldNotFound: 'That field no longer exists.',

  cropNameRequired: 'Crop name is required.',
  cropNameDuplicate: (name: string) => `A crop named "${name}" already exists.`,
  cropNotFound: 'That crop no longer exists.',

  varietyNameRequired: 'Variety name is required.',
  varietyCropMissing: 'Select a crop for this variety.',
  varietyCropNotFound: 'The selected crop does not exist.',
  varietyNotFound: 'That variety no longer exists.',

  unitNameRequired: 'Unit name is required.',
  unitCategoryRequired:
    'A base measure category (mass, volume, or count) is required.',
  unitCategoryInvalid: 'Base measure must be one of: mass, volume, count.',
  unitNameDuplicate: (name: string) => `A unit named "${name}" already exists.`,
  unitNotFound: 'That unit no longer exists.',

  unitMissing: 'Select a unit.',
  unitUnknown: 'That unit does not exist.',
  conversionSelf: 'Choose two different units.',
  conversionFactorInvalid: 'Conversion factor must be a positive number.',
  conversionDuplicate: (from: string, to: string) =>
    `A conversion rule from "${from}" to "${to}" already exists.`,

  quantityNotNumeric: 'Quantity must be a number.',
  categoryMismatch: (
    from: string,
    fromCategory: string,
    to: string,
    toCategory: string,
  ) =>
    `Cannot convert "${from}" (${fromCategory}) to "${to}" (${toCategory}): base measures do not match.`,
  noConversionRule: (from: string, to: string) =>
    `No rule exists for converting from "${from}" to "${to}".`,
} as const;

/**
 * Parses a submitted area into a number, or throws the backend's error
 * (400, with the offending field) exactly as the API would.
 */
export function parseArea(value: string | number): number {
  const trimmed = typeof value === 'string' ? value.trim() : '';
  const numeric =
    typeof value === 'number'
      ? value
      : trimmed === ''
        ? Number.NaN
        : Number(trimmed);

  if (!Number.isFinite(numeric)) {
    throw new ApiError(SETUP_ERRORS.areaNotNumeric, 400, 'area');
  }

  if (numeric < 0) {
    throw new ApiError(SETUP_ERRORS.areaNegative, 400, 'area');
  }

  return numeric;
}

/** Parses a conversion factor; zero, negative, and non-numeric all fail. */
export function parseFactor(value: string | number): number {
  const numeric =
    typeof value === 'number' ? value : Number(String(value).trim());

  if (!Number.isFinite(numeric) || numeric <= 0) {
    throw new ApiError(SETUP_ERRORS.conversionFactorInvalid, 400, 'factor');
  }

  return numeric;
}

/** Parses a conversion quantity; must be a finite number. */
export function parseQuantity(value: string | number): number {
  const trimmed = typeof value === 'string' ? value.trim() : '';
  const numeric =
    typeof value === 'number'
      ? value
      : trimmed === ''
        ? Number.NaN
        : Number(trimmed);

  if (!Number.isFinite(numeric)) {
    throw new ApiError(SETUP_ERRORS.quantityNotNumeric, 400, 'quantity');
  }

  return numeric;
}
