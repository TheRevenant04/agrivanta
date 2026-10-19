import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/authContext';
import { useServices } from '../services/servicesContext';

/** Protected landing route rendered for authenticated users. */
export function DashboardPage() {
  const { user, signOut } = useAuth();
  const services = useServices();
  const navigate = useNavigate();
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);

    try {
      await services.auth.logout();
    } catch {
      // Clear the local session even if the request fails.
    } finally {
      signOut();
      setSigningOut(false);
      navigate('/login', { replace: true });
    }
  }

  return (
    <main>
      <h1>Dashboard</h1>
      <p>Signed in as {user?.email}</p>
      {user ? <p>Role: {user.role}</p> : null}
      <button type="button" onClick={handleSignOut} disabled={signingOut}>
        {signingOut ? 'Signing out…' : 'Sign out'}
      </button>
    </main>
  );
}
