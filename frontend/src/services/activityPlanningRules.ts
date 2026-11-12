/**
 * Backend validation rules for the activity planning domains, mirrored in
 * one place so the mock implementation, the parity fake backend, and the
 * UI forms all agree on messages and status codes.
 *
 * The rules mirror the endpoints described in issues #13, #14, and #15:
 * a blank planned date, a missing or unknown activity type, a missing
 * cycle, malformed resource needs, and an illegal status transition are
 * all rejected with a clear error before anything is persisted. Overdue
 * detection itself is server-side (issue #37); the UI only renders the
 * `overdue` status the API reports.
 */

import {
  ApiError,
  type ActivityCategory,
  type ActivityStatus,
} from '@/services/types';

export const ACTIVITY_CATEGORIES: readonly ActivityCategory[] = [
  'land preparation',
  'planting',
  'fertilizing',
  'spraying',
  'harvesting',
  'custom',
];

export function isActivityCategory(value: string): value is ActivityCategory {
  return (ACTIVITY_CATEGORIES as readonly string[]).includes(value);
}

export function isActivityStatus(value: string): value is ActivityStatus {
  return (
    value === 'planned' ||
    value === 'in_progress' ||
    value === 'completed' ||
    value === 'overdue'
  );
}

/** The five templates seeded on farm creation (issue #13). */
export const STANDARD_ACTIVITY_TEMPLATES: readonly {
  name: string;
  category: ActivityCategory;
}[] = [
  { name: 'Land preparation', category: 'land preparation' },
  { name: 'Planting', category: 'planting' },
  { name: 'Fertilizing', category: 'fertilizing' },
  { name: 'Spraying', category: 'spraying' },
  { name: 'Harvesting', category: 'harvesting' },
];

/**
 * Item names the resource-needs form can pick from while the inventory
 * domain (issue #16) does not exist yet; the backend will replace this
 * with the real inventory item list.
 */
export const INVENTORY_ITEM_OPTIONS: readonly string[] = [
  'Seed',
  'Fertilizer',
  'Pesticide',
  'Fuel',
  'Irrigation water',
];

/** Single source of truth for activity planning validation messages. */
export const ACTIVITY_ERRORS = {
  activityTypeMissing: 'Select an activity type.',
  activityTypeUnknown: 'The selected activity type does not exist.',
  activityTypeNotFound: 'That activity type no longer exists.',
  activityTypeNameRequired: 'Template name is required.',
  activityTypeCategoryRequired: 'A template category is required.',
  activityTypeCategoryInvalid:
    'Category must be one of: land preparation, planting, fertilizing, spraying, harvesting, custom.',
  activityTypeDuplicate: (name: string) =>
    `A template named "${name}" already exists.`,

  cycleMissing: 'Select a crop cycle.',
  cycleUnknown: 'The selected crop cycle does not exist.',

  plannedDateRequired: 'Planned date is required.',
  plannedDateInvalid: 'Planned date must be a valid calendar date.',

  labourHoursRequired: 'Labour hours are required.',
  labourHoursNotNumeric: 'Labour hours must be a number.',
  labourHoursNegative: 'Labour hours cannot be negative.',

  itemNameRequired: 'Each input row needs an item name.',
  quantityNotNumeric: 'Quantity must be a number.',
  quantityNotPositive: 'Quantity must be greater than zero.',

  activityNotFound: 'That activity no longer exists.',
  statusInvalid:
    'Status must be one of: planned, in progress, completed, overdue.',
  statusTransitionInvalid: (from: ActivityStatus, to: string) =>
    `Cannot move an activity from "${statusLabel(from)}" to "${to.trim()}".`,
} as const;

/** Human-facing label for a status, used by badges and error messages. */
export function statusLabel(status: ActivityStatus): string {
  return status === 'in_progress' ? 'in progress' : status;
}

/**
 * Allowed status transitions. Overdue detection is a server job (#37);
 * once an activity is flagged overdue it can still be started.
 */
export const ACTIVITY_TRANSITIONS: Readonly<
  Record<ActivityStatus, readonly ActivityStatus[]>
> = {
  planned: ['in_progress'],
  in_progress: ['completed'],
  overdue: ['in_progress'],
  completed: [],
};

export function canTransition(
  from: ActivityStatus,
  to: ActivityStatus,
): boolean {
  return ACTIVITY_TRANSITIONS[from].includes(to);
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Parses a submitted planned date into the normalised ISO string, or
 * throws the backend's error (400, with the offending field) exactly as
 * the API would.
 */
export function parsePlannedDate(value: string): string {
  const trimmed = value.trim();

  if (!trimmed) {
    throw new ApiError(ACTIVITY_ERRORS.plannedDateRequired, 400, 'plannedDate');
  }

  if (!ISO_DATE.test(trimmed) || Number.isNaN(Date.parse(trimmed))) {
    throw new ApiError(ACTIVITY_ERRORS.plannedDateInvalid, 400, 'plannedDate');
  }

  return trimmed;
}

/** Parses planned labour hours; blank, non-numeric, and negative fail. */
export function parseLabourHours(value: string | number): number {
  if (typeof value === 'string' && value.trim() === '') {
    throw new ApiError(ACTIVITY_ERRORS.labourHoursRequired, 400, 'labourHours');
  }

  const numeric =
    typeof value === 'number' ? value : Number(String(value).trim());

  if (!Number.isFinite(numeric)) {
    throw new ApiError(
      ACTIVITY_ERRORS.labourHoursNotNumeric,
      400,
      'labourHours',
    );
  }

  if (numeric < 0) {
    throw new ApiError(ACTIVITY_ERRORS.labourHoursNegative, 400, 'labourHours');
  }

  return numeric;
}

/** Parses a planned input quantity; blank, non-numeric, and <= 0 fail. */
export function parseNeedQuantity(value: string | number): number {
  const trimmed = typeof value === 'string' ? value.trim() : '';
  const numeric =
    typeof value === 'number'
      ? value
      : trimmed === ''
        ? Number.NaN
        : Number(trimmed);

  if (!Number.isFinite(numeric)) {
    throw new ApiError(ACTIVITY_ERRORS.quantityNotNumeric, 400, 'inputs');
  }

  if (numeric <= 0) {
    throw new ApiError(ACTIVITY_ERRORS.quantityNotPositive, 400, 'inputs');
  }

  return numeric;
}
