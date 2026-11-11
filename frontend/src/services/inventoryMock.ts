import {
  INVENTORY_ERRORS,
  isMovementType,
  parseMovementQuantity,
  parseReorderLevel,
} from './inventoryRules';
import {
  ApiError,
  UnauthorizedError,
  type InventoryItem,
  type InventoryItemInput,
  type InventoryServices,
  type StockMovement,
  type StockMovementInput,
  type Unit,
} from '@/services/types';

/**
 * Seed shape for the inventory domain. Items carry no quantity: the
 * current quantity is always derived from the movements (seeded ones
 * included), mirroring backend issue #16. Omitted collections start empty
 * so the list renders its empty state.
 */
export type InventorySeedItem = Omit<InventoryItem, 'currentQuantity'>;

export interface InventorySeed {
  items?: InventorySeedItem[];
  movements?: StockMovement[];
}

export interface InventoryMockOptions {
  seed?: InventorySeed;
  /**
   * Called before every request, mirroring the backend's 401 rule. Defaults
   * to rejecting like an unauthenticated API call; `createMockServices`
   * wires this to the stored session.
   */
  requireAuth?: () => void;
  /**
   * Resolves a unit by id so the backend's "unit must exist" rule can be
   * mirrored. Defaults to resolving nothing, so no unit id validates.
   */
  findUnit?: (id: string) => Promise<Unit | null>;
}

/**
 * In-memory implementation of the inventory domains. It enforces the same
 * rules (messages, 400/404 status codes, offending field) as the HTTP
 * implementation, and every item's current quantity is derived from its
 * movements — there is no manually maintained balance.
 */
export function createInventoryMock(
  options: InventoryMockOptions = {},
): InventoryServices {
  const requireAuth =
    options.requireAuth ??
    (() => {
      throw new UnauthorizedError();
    });
  const findUnit = options.findUnit ?? (() => Promise.resolve(null));
  const seed = options.seed ?? {};

  type StoredItem = Omit<InventoryItem, 'currentQuantity'>;
  type ItemAttributes = Omit<StoredItem, 'id'>;

  const items: StoredItem[] = (seed.items ?? []).map((item) => ({ ...item }));
  const movements: StockMovement[] = (seed.movements ?? []).map((movement) => ({
    ...movement,
  }));

  let itemSequence = items.length;
  let movementSequence = movements.length;

  /** Signed stock effect of one movement: usage removes, others add. */
  function movementDelta(movement: StockMovement): number {
    return movement.type === 'usage' ? -movement.quantity : movement.quantity;
  }

  function quantityOf(itemId: string): number {
    return movements
      .filter((movement) => movement.itemId === itemId)
      .reduce((total, movement) => total + movementDelta(movement), 0);
  }

  function withQuantity(item: StoredItem): InventoryItem {
    return { ...item, currentQuantity: quantityOf(item.id) };
  }

  function requireName(value: string): string {
    const name = value.trim();

    if (!name) {
      throw new ApiError(INVENTORY_ERRORS.itemNameRequired, 400, 'name');
    }

    return name;
  }

  async function requireUnit(unitId: string): Promise<string> {
    const trimmed = unitId.trim();

    if (!trimmed) {
      throw new ApiError(INVENTORY_ERRORS.itemUnitMissing, 400, 'unitId');
    }

    const unit = await findUnit(trimmed);

    if (!unit) {
      throw new ApiError(INVENTORY_ERRORS.itemUnitUnknown, 404, 'unitId');
    }

    return unit.id;
  }

  async function validateItemInput(
    input: InventoryItemInput,
  ): Promise<ItemAttributes> {
    return {
      name: requireName(input.name),
      unitId: await requireUnit(input.unitId),
      reorderLevel: parseReorderLevel(input.reorderLevel),
    };
  }

  return {
    items: {
      async list() {
        requireAuth();
        return items.map(withQuantity);
      },

      async create(input: InventoryItemInput) {
        requireAuth();
        itemSequence += 1;
        const created: StoredItem = {
          id: `item-${itemSequence}`,
          ...(await validateItemInput(input)),
        };
        items.push(created);
        return withQuantity(created);
      },

      async update(id: string, input: InventoryItemInput) {
        requireAuth();
        const index = items.findIndex((item) => item.id === id);

        if (index === -1) {
          throw new ApiError(INVENTORY_ERRORS.itemNotFound, 404);
        }

        items[index] = {
          ...items[index],
          ...(await validateItemInput(input)),
        };
        return withQuantity(items[index]);
      },
    },

    movements: {
      async list(itemId?: string) {
        requireAuth();
        return movements
          .filter((movement) => (itemId ? movement.itemId === itemId : true))
          .map((movement) => ({ ...movement }));
      },

      async create(input: StockMovementInput) {
        requireAuth();
        const index = items.findIndex((item) => item.id === input.itemId);

        if (index === -1) {
          throw new ApiError(
            INVENTORY_ERRORS.movementItemUnknown,
            404,
            'itemId',
          );
        }

        if (!isMovementType(input.type)) {
          throw new ApiError(INVENTORY_ERRORS.movementTypeInvalid, 400, 'type');
        }

        const quantity = parseMovementQuantity(input.quantity, input.type);
        const available = quantityOf(items[index].id);

        if (input.type === 'usage' && quantity > available) {
          throw new ApiError(
            INVENTORY_ERRORS.usageExceeds(available),
            400,
            'quantity',
          );
        }

        movementSequence += 1;
        const created: StockMovement = {
          id: `movement-${movementSequence}`,
          itemId: items[index].id,
          type: input.type,
          quantity,
          ...(input.date?.trim() ? { date: input.date.trim() } : {}),
          ...(input.note?.trim() ? { note: input.note.trim() } : {}),
        };
        movements.push(created);
        return { ...created };
      },
    },
  };
}
