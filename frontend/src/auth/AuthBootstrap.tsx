import { useEffect, type ReactNode } from 'react';
import { useServices } from '../services/servicesContext';
import { useAuth } from './authContext';

/**
 * Revalidates a stored token on boot by calling `me()`. If the token is
 * rejected, the services provider's 401 guard clears the session and the
 * route guard redirects to login with a message.
 */
export function AuthBootstrap({ children }: { children: ReactNode }) {
  const { token, user, signIn } = useAuth();
  const services = useServices();
  const userId = user?.id;

  useEffect(() => {
    if (!token || !userId) {
      return;
    }

    let active = true;

    services.auth
      .me()
      .then((freshUser) => {
        if (active) {
          signIn({ token, user: freshUser });
        }
      })
      .catch(() => {
        // A 401 is handled by the services provider's unauthorized guard.
      });

    return () => {
      active = false;
    };
  }, [token, userId, services, signIn]);

  return <>{children}</>;
}
