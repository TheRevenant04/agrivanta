import { createContext, useContext } from 'react';
import type { AgrivantaServices } from '@/services/types';

export const ServicesContext = createContext<AgrivantaServices | null>(null);

/** Access the single services layer. Must be used within a ServicesProvider. */
export function useServices(): AgrivantaServices {
  const services = useContext(ServicesContext);

  if (!services) {
    throw new Error('useServices must be used within a ServicesProvider');
  }

  return services;
}
