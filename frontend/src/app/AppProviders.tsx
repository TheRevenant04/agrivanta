import type { ReactNode } from 'react';
import { AuthProvider } from '../auth/AuthProvider';
import { useAuth } from '../auth/authContext';
import { ServicesProvider } from '../services/ServicesProvider';
import type { SessionStore } from '../services/sessionStore';
import type { AgrivantaServices } from '../services/types';

function AuthenticatedServices({
  children,
  services,
}: {
  children: ReactNode;
  services?: AgrivantaServices;
}) {
  const { handleUnauthorized } = useAuth();

  return (
    <ServicesProvider services={services} onUnauthorized={handleUnauthorized}>
      {children}
    </ServicesProvider>
  );
}

export interface AppProvidersProps {
  children: ReactNode;
  services?: AgrivantaServices;
  store?: SessionStore;
}

/** Composes auth state and the services layer, in that order. */
export function AppProviders({ children, services, store }: AppProvidersProps) {
  return (
    <AuthProvider store={store}>
      <AuthenticatedServices services={services}>
        {children}
      </AuthenticatedServices>
    </AuthProvider>
  );
}
