import { BrowserRouter } from 'react-router-dom';
import { AppProviders } from './app/AppProviders';
import { AppRoutes } from './app/AppRoutes';
import type { SessionStore } from './services/sessionStore';
import type { AgrivantaServices } from './services/types';

export interface AppProps {
  /** Injectable services, used by tests; defaults to the env-selected client. */
  services?: AgrivantaServices;
  /** Injectable session store, used by tests; defaults to localStorage. */
  store?: SessionStore;
}

export function App({ services, store }: AppProps = {}) {
  return (
    <AppProviders services={services} store={store}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AppProviders>
  );
}
