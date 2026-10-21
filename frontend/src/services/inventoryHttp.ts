import type { ServiceRequest } from './farmSetupHttp';
import type {
  InventoryItem,
  InventoryItemInput,
  InventoryServices,
  StockMovement,
  StockMovementInput,
} from './types';

function body(input: unknown): RequestInit {
  return { method: 'POST', body: JSON.stringify(input) };
}

function put(input: unknown): RequestInit {
  return { method: 'PUT', body: JSON.stringify(input) };
}

/**
 * HTTP implementation of the inventory domains. Thin, typed wrappers over
 * the routes backend issue #16 exposes: `/inventory-items` for items and
 * the nested `/inventory-items/:id/movements` for stock movements
 * (`/stock-movements` lists movements across items). Error status codes
 * and messages are surfaced by the shared response mapper in
 * `httpServices.ts`.
 */
export function createInventoryHttp(
  request: ServiceRequest,
): InventoryServices {
  return {
    items: {
      list: () =>
        request<InventoryItem[]>('/inventory-items', { method: 'GET' }, true),
      create: (input: InventoryItemInput) =>
        request<InventoryItem>('/inventory-items', body(input), true),
      update: (id: string, input: InventoryItemInput) =>
        request<InventoryItem>(
          `/inventory-items/${encodeURIComponent(id)}`,
          put(input),
          true,
        ),
    },

    movements: {
      list: (itemId?: string) =>
        request<StockMovement[]>(
          itemId
            ? `/inventory-items/${encodeURIComponent(itemId)}/movements`
            : '/stock-movements',
          { method: 'GET' },
          true,
        ),
      create: (input: StockMovementInput) =>
        request<StockMovement>(
          `/inventory-items/${encodeURIComponent(input.itemId)}/movements`,
          body(input),
          true,
        ),
    },
  };
}
