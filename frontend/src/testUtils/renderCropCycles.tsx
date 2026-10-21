import { render } from '@testing-library/react';
import { App } from '../App';
import type { FarmSetupSeed } from '../services/farmSetupMock';
import { MOCK_USERS, createMockServices } from '../services/mockServices';
import {
  createSessionStore,
  type SessionStore,
} from '../services/sessionStore';
import type { AgrivantaServices, CropCycle } from '../services/types';

export interface RenderCropCyclesOptions {
  /** The route to open before rendering; defaults to `/cycles`. */
  route?: string;
  /** Seed for the mock farm setup domains; defaults are empty collections. */
  farmSetup?: FarmSetupSeed;
  /** Seed crop cycles; defaults to none. */
  cropCycles?: CropCycle[];
}

export interface RenderCropCyclesResult {
  services: AgrivantaServices;
  store: SessionStore;
}

/**
 * Renders the app authenticated as the seed owner on the crop cycle
 * screens, with mock services seeded for both the farm setup domains and
 * the crop cycle domain (issue #45).
 */
export async function renderCropCycleScreen(
  options: RenderCropCyclesOptions = {},
): Promise<RenderCropCyclesResult> {
  window.localStorage.clear();

  const store = createSessionStore(window.localStorage);
  const services = createMockServices({
    store,
    farmSetup: options.farmSetup,
    cropCycles: options.cropCycles,
  });

  await services.auth.login({
    email: MOCK_USERS[0].email,
    password: MOCK_USERS[0].password,
  });

  window.history.pushState({}, '', options.route ?? '/cycles');
  render(<App services={services} store={store} />);

  return { services, store };
}
