import {
  parseHarvestQuantity,
  parseRecordDate,
  parseSaleQuantity,
  parseUnitPrice,
  HARVEST_ERRORS,
  SALE_ERRORS,
} from './harvestSaleRules';
import {
  ApiError,
  UnauthorizedError,
  type Harvest,
  type HarvestCycleRef,
  type HarvestInput,
  type HarvestSaleServices,
  type Sale,
  type SaleCustomer,
  type SaleInput,
} from '@/services/types';

/**
 * Seed shape for the harvest and sale domains. Omitted collections start
 * empty (so every cycle renders its empty state); the cycle picker and the
 * customer picker fall back to the demo entries below.
 */
export interface HarvestSaleCycleSeed extends HarvestCycleRef {
  /** Closed cycles reject new harvests, mirroring the backend rule (#28). */
  status?: 'open' | 'closed';
}

export interface SaleSeed extends Omit<Sale, 'revenue'> {
  /** Defaults to quantity × unit price when omitted. */
  revenue?: number;
}

export interface HarvestSaleSeed {
  cycles?: HarvestSaleCycleSeed[];
  customers?: SaleCustomer[];
  harvests?: Harvest[];
  sales?: SaleSeed[];
}

export interface HarvestSaleMockOptions {
  seed?: HarvestSaleSeed;
  /**
   * Called before every request, mirroring the backend's 401 rule. Defaults
   * to rejecting like an unauthenticated API call; `createMockServices`
   * wires this to the stored session.
   */
  requireAuth?: () => void;
}

/** The crop cycles the demo farm records harvests and sales against. */
export const DEFAULT_HARVEST_CYCLES: readonly HarvestSaleCycleSeed[] = [
  { id: 'cycle-1', label: 'North 40 — Wheat 2026', status: 'open' },
  { id: 'cycle-2', label: 'South 12 — Maize 2026', status: 'open' },
];

/** The customer profiles the demo sale form offers. */
export const DEFAULT_SALE_CUSTOMERS: readonly SaleCustomer[] = [
  { id: 'customer-1', name: 'Greenfield Grain Co.' },
  { id: 'customer-2', name: 'Harbour Mill' },
];

function roundAmount(value: number): number {
  return Math.round(value * 10000) / 10000;
}

function copy<T extends object>(item: T): T {
  return { ...item };
}

/**
 * In-memory implementation of the harvest and sale domains. It enforces the
 * same rules (messages, 400/404 status codes, offending field) as the HTTP
 * implementation, so callers cannot tell them apart.
 */
export function createHarvestSaleMock(
  options: HarvestSaleMockOptions = {},
): HarvestSaleServices {
  const requireAuth =
    options.requireAuth ??
    (() => {
      throw new UnauthorizedError();
    });
  const seed = options.seed ?? {};

  const cycles: HarvestSaleCycleSeed[] = (
    seed.cycles ?? DEFAULT_HARVEST_CYCLES
  ).map((item) => ({ ...item }));
  const customers: SaleCustomer[] = (
    seed.customers ?? DEFAULT_SALE_CUSTOMERS
  ).map((item) => ({ ...item }));
  const harvests: Harvest[] = (seed.harvests ?? []).map((item) => ({
    ...item,
  }));
  const sales: Sale[] = (seed.sales ?? []).map((item) => ({
    ...item,
    revenue: item.revenue ?? roundAmount(item.quantity * item.unitPrice),
  }));

  const sequence = {
    harvest: harvests.length,
    sale: sales.length,
  };

  function nextId(kind: keyof typeof sequence): string {
    sequence[kind] += 1;
    return `${kind}-${sequence[kind]}`;
  }

  function findCycle(id: string): HarvestSaleCycleSeed {
    if (!id) {
      throw new ApiError(HARVEST_ERRORS.cycleRequired, 400, 'cycleId');
    }

    const cycle = cycles.find((item) => item.id === id);

    if (!cycle) {
      throw new ApiError(HARVEST_ERRORS.cycleNotFound, 404, 'cycleId');
    }

    return cycle;
  }

  function findCustomer(id: string): SaleCustomer {
    if (!id) {
      throw new ApiError(SALE_ERRORS.customerRequired, 400, 'customerId');
    }

    const customer = customers.find((item) => item.id === id);

    if (!customer) {
      throw new ApiError(SALE_ERRORS.customerNotFound, 400, 'customerId');
    }

    return customer;
  }

  function findHarvest(id: string): Harvest {
    if (!id) {
      throw new ApiError(SALE_ERRORS.harvestRequired, 400, 'harvestId');
    }

    const harvest = harvests.find((item) => item.id === id);

    if (!harvest) {
      throw new ApiError(SALE_ERRORS.harvestNotFound, 400, 'harvestId');
    }

    return harvest;
  }

  /** Harvested quantity minus everything already sold from that harvest. */
  function remainingUnsold(harvest: Harvest): number {
    const sold = sales
      .filter((item) => item.harvestId === harvest.id)
      .reduce((sum, item) => sum + item.quantity, 0);

    return roundAmount(harvest.quantity - sold);
  }

  return {
    harvests: {
      async listCycles() {
        requireAuth();
        return cycles.map((cycle) => ({ id: cycle.id, label: cycle.label }));
      },

      async list(cycleId?: string) {
        requireAuth();
        return harvests
          .filter((item) => (cycleId ? item.cycleId === cycleId : true))
          .map(copy);
      },

      async create(input: HarvestInput) {
        requireAuth();
        const cycle = findCycle(input.cycleId);

        if (cycle.status === 'closed') {
          throw new ApiError(HARVEST_ERRORS.cycleClosed, 400, 'cycleId');
        }

        const quantity = parseHarvestQuantity(input.quantity);
        const unitId = input.unitId.trim();

        if (!unitId) {
          throw new ApiError(HARVEST_ERRORS.unitRequired, 400, 'unitId');
        }

        const date = parseRecordDate(input.date);
        const created: Harvest = {
          id: nextId('harvest'),
          cycleId: cycle.id,
          quantity,
          unitId,
          date,
        };
        harvests.push(created);
        return copy(created);
      },
    },

    sales: {
      async listCustomers() {
        requireAuth();
        return customers.map(copy);
      },

      async list() {
        requireAuth();
        return sales.map(copy);
      },

      async create(input: SaleInput) {
        requireAuth();
        const customer = findCustomer(input.customerId);
        const harvest = findHarvest(input.harvestId);
        const quantity = parseSaleQuantity(input.quantity);
        const unitPrice = parseUnitPrice(input.unitPrice);
        const date = parseRecordDate(input.date);

        const available = remainingUnsold(harvest);

        if (quantity > available) {
          throw new ApiError(
            SALE_ERRORS.soldExceedsHarvested(available),
            400,
            'quantity',
          );
        }

        const created: Sale = {
          id: nextId('sale'),
          customerId: customer.id,
          harvestId: harvest.id,
          quantity,
          unitPrice,
          date,
          revenue: roundAmount(quantity * unitPrice),
        };
        sales.push(created);
        return copy(created);
      },
    },
  };
}
