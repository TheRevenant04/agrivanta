/**
 * Backend validation rules for the inventory domains, mirrored in one
 * place so the mock implementation, the parity fake backend, and the UI
 * forms all agree on messages and status codes.
 *
 * The rules mirror the endpoints described in backend issue #16: a blank
 * item name, a missing or unknown unit, a non-numeric or negative reorder
 * level, and a movement that is not a valid number, is non-positive, or
 * would drive stock below zero are all rejected with a clear error before
 * anything is persisted.
 */

import { ApiError, type InventoryItem, type StockMovementType } from '@/services/types';

/** Movement types the backend accepts. */
export const MOVEMENT_TYPES: readonly StockMovementType[] = [
  'purchase',
  'usage',
  'adjustment',
];

export function isMovementType(value: string): value is StockMovementType {
  return (MOVEMENT_TYPES as readonly string[]).includes(value);
}

/** Single source of truth for inventory validation messages. */
export const INVENTORY_ERRORS = {
  itemNameRequired: 'Inventory item name is required.',
  itemUnitMissing: 'Select a unit.',
  itemUnitUnknown: 'That unit does not exist.',
  itemNotFound: 'That inventory item no longer exists.',
  reorderNotNumeric: 'Reorder level must be a number.',
  reorderNegative: 'Reorder level cannot be negative.',

  movementItemUnknown: 'That inventory item does not exist.',
  movementTypeInvalid:
    'Movement type must be one of: purchase, usage, adjustment.',
  quantityNotNumeric: 'Quantity must be a number.',
  quantityNotPositive: 'Quantity must be a positive number.',
  adjustmentZero: 'Adjustment quantity cannot be zero.',
  usageExceeds: (available: number) =>
    `Usage exceeds the available quantity (available: ${available}).`,
} as const;

/**
 * Parses a submitted reorder level into a number, or throws the backend's
 * error (400, with the offending field) exactly as the API would.
 */
export function parseReorderLevel(value: string | number): number {
  const trimmed = typeof value === 'string' ? value.trim() : '';
  const numeric =
    typeof value === 'number'
      ? value
      : trimmed === ''
        ? Number.NaN
        : Number(trimmed);

  if (!Number.isFinite(numeric)) {
    throw new ApiError(INVENTORY_ERRORS.reorderNotNumeric, 400, 'reorderLevel');
  }

  if (numeric < 0) {
    throw new ApiError(INVENTORY_ERRORS.reorderNegative, 400, 'reorderLevel');
  }

  return numeric;
}

/**
 * Parses a movement quantity for its type: purchases and usages must be
 * positive, while adjustments are signed (a negative adjustment removes
 * stock) but cannot be zero.
 */
export function parseMovementQuantity(
  value: string | number,
  type: StockMovementType,
): number {
  const trimmed = typeof value === 'string' ? value.trim() : '';
  const numeric =
    typeof value === 'number'
      ? value
      : trimmed === ''
        ? Number.NaN
        : Number(trimmed);

  if (!Number.isFinite(numeric)) {
    throw new ApiError(INVENTORY_ERRORS.quantityNotNumeric, 400, 'quantity');
  }

  if (type === 'adjustment') {
    if (numeric === 0) {
      throw new ApiError(INVENTORY_ERRORS.adjustmentZero, 400, 'quantity');
    }
    return numeric;
  }

  if (numeric <= 0) {
    throw new ApiError(INVENTORY_ERRORS.quantityNotPositive, 400, 'quantity');
  }

  return numeric;
}

/**
 * The low-stock rule: an item is low when its derived quantity is at or
 * below its reorder level, so a reorder level of 0 only flags an item that
 * is actually out of stock.
 */
export function isLowStock(
  item: Pick<InventoryItem, 'currentQuantity' | 'reorderLevel'>,
): boolean {
  return item.currentQuantity <= item.reorderLevel;
}
