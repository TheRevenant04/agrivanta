import type { ServiceRequest } from './farmSetupHttp';
import type {
  Harvest,
  HarvestCycleRef,
  HarvestInput,
  HarvestSaleServices,
  Sale,
  SaleCustomer,
  SaleInput,
} from '@/services/types';

function body(input: unknown): RequestInit {
  return { method: 'POST', body: JSON.stringify(input) };
}

/**
 * HTTP implementation of the harvest and sale domains. Thin, typed wrappers
 * over the REST endpoints the backend tasks (#28, #29, and the #19 customer
 * profiles) provide; error status codes and messages are surfaced by the
 * shared response mapper in `httpServices.ts`.
 */
export function createHarvestSaleHttp(
  request: ServiceRequest,
): HarvestSaleServices {
  return {
    harvests: {
      listCycles: () =>
        request<HarvestCycleRef[]>('/harvests/cycles', { method: 'GET' }, true),
      list: (cycleId?: string) =>
        request<Harvest[]>(
          cycleId
            ? `/harvests?cycle=${encodeURIComponent(cycleId)}`
            : '/harvests',
          { method: 'GET' },
          true,
        ),
      create: (input: HarvestInput) =>
        request<Harvest>('/harvests', body(input), true),
    },

    sales: {
      listCustomers: () =>
        request<SaleCustomer[]>('/customers', { method: 'GET' }, true),
      list: () => request<Sale[]>('/sales', { method: 'GET' }, true),
      create: (input: SaleInput) => request<Sale>('/sales', body(input), true),
    },
  };
}
