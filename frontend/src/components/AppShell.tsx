import { Sprout } from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { NotificationBell } from './NotificationBell';

interface NavItem {
  to: string;
  label: string;
}

interface NavGroup {
  label: string;
  links: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Overview',
    links: [
      { to: '/dashboard', label: 'Dashboard' },
      { to: '/chat', label: 'AI analyst' },
      { to: '/reports', label: 'Reports' },
    ],
  },
  {
    label: 'Farm setup',
    links: [
      { to: '/farm', label: 'Farm' },
      { to: '/setup', label: 'Guided setup' },
      { to: '/fields', label: 'Fields' },
      { to: '/crops', label: 'Crops' },
      { to: '/varieties', label: 'Varieties' },
      { to: '/units', label: 'Units' },
      { to: '/conversions', label: 'Conversions' },
      { to: '/cycles', label: 'Crop cycles' },
    ],
  },
  {
    label: 'Operations',
    links: [
      { to: '/activities', label: 'Activities' },
      { to: '/activity-templates', label: 'Templates' },
      { to: '/inventory', label: 'Inventory' },
      { to: '/imports', label: 'Imports' },
    ],
  },
  {
    label: 'Finance',
    links: [
      { to: '/expenses', label: 'Expenses' },
      { to: '/payments', label: 'Payments' },
      { to: '/harvests', label: 'Harvests' },
      { to: '/sales', label: 'Sales' },
    ],
  },
];

/**
 * Authenticated app shell: a persistent sidebar for navigation and a header
 * with account-level actions, with the matched route rendered underneath.
 */
export function AppShell() {
  return (
    <div className="min-h-screen bg-muted/30 lg:grid lg:grid-cols-[16rem_1fr]">
      <aside className="border-b bg-sidebar text-sidebar-foreground lg:border-b-0 lg:border-r">
        <div className="flex h-16 items-center gap-2 px-6">
          <span className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Sprout className="size-5" aria-hidden="true" />
          </span>
          <span className="text-lg font-semibold tracking-tight">
            Agrivanta
          </span>
        </div>

        <nav
          aria-label="Main"
          className="space-y-6 px-3 pb-6 lg:sticky lg:top-0 lg:max-h-[calc(100vh-4rem)] lg:overflow-y-auto"
        >
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <p className="px-3 pb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {group.label}
              </p>
              <div className="space-y-1">
                {group.links.map((link) => (
                  <NavLink
                    key={link.to}
                    to={link.to}
                    className={({ isActive }) =>
                      cn(
                        'block rounded-md px-3 py-2 text-sm font-medium transition-colors',
                        isActive
                          ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                          : 'text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground',
                      )
                    }
                  >
                    {link.label}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="flex h-16 items-center justify-between gap-4 border-b bg-background px-4 sm:px-6">
          <p className="text-sm text-muted-foreground">
            Farm operations &amp; profitability
          </p>
          <NotificationBell />
        </header>

        <main className="flex-1 p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
