import { render } from '@testing-library/react';
import { App } from '../App';
import type { FarmSetupSeed } from '../services/farmSetupMock';
import type { HarvestSaleSeed } from '../services/harvestSaleMock';
import { MOCK_USERS, createMockServices } from '../services/mockServices';
import {
  createSessionStore,
  type SessionStore,
} from '../services/sessionStore';
import type { AgrivantaServices } from '../services/types';

export interface RenderHarvestSaleOptions {
  /** The route to open before rendering, e.g. `/harvests`. */
  route: string;
  /** Seed for the units shown by the harvest/sale forms. */
  farmSetup?: FarmSetupSeed;
  /** Seed for the cycles, customers, harvests, and sales. */
  harvestSale?: HarvestSaleSeed;
}

export interface RenderHarvestSaleResult {
  services: AgrivantaServices;
  store: SessionStore;
}

/**
 * Renders the app authenticated as the seed owner on the given harvest or
 * sale route, with mock services seeded for both the farm setup units and
 * the harvest/sale domains.
 */
export async function renderHarvestSaleScreen(
  options: RenderHarvestSaleOptions,
): Promise<RenderHarvestSaleResult> {
  window.localStorage.clear();

  const store = createSessionStore(window.localStorage);
  const services = createMockServices({
    store,
    farmSetup: options.farmSetup,
    harvestSale: options.harvestSale,
  });

  await services.auth.login({
    email: MOCK_USERS[0].email,
    password: MOCK_USERS[0].password,
  });

  window.history.pushState({}, '', options.route);
  render(<App services={services} store={store} />);

  return { services, store };
}
