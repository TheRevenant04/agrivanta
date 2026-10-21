import { render } from '@testing-library/react';
import { App } from '../App';
import type { FarmSetupSeed } from '../services/farmSetupMock';
import type { InventorySeed } from '../services/inventoryMock';
import { MOCK_USERS, createMockServices } from '../services/mockServices';
import {
  createSessionStore,
  type SessionStore,
} from '../services/sessionStore';
import type { AgrivantaServices } from '../services/types';

export interface RenderSetupOptions {
  /** The route to open before rendering, e.g. `/fields`. */
  route: string;
  /** Seed for the mock farm setup domains; defaults are empty collections. */
  seed?: FarmSetupSeed;
  /** Seed for the mock inventory domain (issue #47). */
  inventory?: InventorySeed;
}

export interface RenderSetupResult {
  services: AgrivantaServices;
  store: SessionStore;
}

/**
 * Renders the app authenticated as the seed owner on the given route, with
 * mock services seeded for the farm setup screens.
 */
export async function renderSetupScreen(
  options: RenderSetupOptions,
): Promise<RenderSetupResult> {
  window.localStorage.clear();

  const store = createSessionStore(window.localStorage);
  const services = createMockServices({
    store,
    farmSetup: options.seed,
    inventory: options.inventory,
  });

  await services.auth.login({
    email: MOCK_USERS[0].email,
    password: MOCK_USERS[0].password,
  });

  window.history.pushState({}, '', options.route);
  render(<App services={services} store={store} />);

  return { services, store };
}
