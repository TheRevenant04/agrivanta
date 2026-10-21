import { render } from '@testing-library/react';
import { App } from '../App';
import type { ExpensePaymentSeed } from '../services/expensePaymentMock';
import { MOCK_USERS, createMockServices } from '../services/mockServices';
import {
  createSessionStore,
  type SessionStore,
} from '../services/sessionStore';
import type { AgrivantaServices } from '../services/types';

export interface RenderExpensesOptions {
  /** The route to open before rendering, e.g. `/expenses`. */
  route: string;
  /** Seed for the expense and payment domains; defaults to empty lists. */
  seed?: ExpensePaymentSeed;
}

export interface RenderExpensesResult {
  services: AgrivantaServices;
  store: SessionStore;
}

/**
 * Renders the app authenticated as the seed owner on the given route, with
 * mock services seeded for the expense and payment screens.
 */
export async function renderExpensesScreen(
  options: RenderExpensesOptions,
): Promise<RenderExpensesResult> {
  window.localStorage.clear();

  const store = createSessionStore(window.localStorage);
  const services = createMockServices({ store, expensePayments: options.seed });

  await services.auth.login({
    email: MOCK_USERS[0].email,
    password: MOCK_USERS[0].password,
  });

  window.history.pushState({}, '', options.route);
  render(<App services={services} store={store} />);

  return { services, store };
}
