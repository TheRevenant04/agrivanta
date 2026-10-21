import { NavLink, Outlet } from 'react-router-dom';

const NAV_LINKS = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/farm', label: 'Farm' },
  { to: '/fields', label: 'Fields' },
  { to: '/crops', label: 'Crops' },
  { to: '/varieties', label: 'Varieties' },
  { to: '/units', label: 'Units' },
  { to: '/expenses', label: 'Expenses' },
  { to: '/payments', label: 'Payments' },
  { to: '/conversions', label: 'Conversions' },
];

/**
 * Authenticated app shell: a top navigation shared by the dashboard and the
 * farm setup screens, with the matched route rendered underneath.
 */
export function AppShell() {
  return (
    <div>
      <header>
        <span>Agrivanta</span>
        <nav aria-label="Main">
          {NAV_LINKS.map((link) => (
            <NavLink key={link.to} to={link.to}>
              {link.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
