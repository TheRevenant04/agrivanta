import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/authContext';
import { ReportingFilter } from '../components/ReportingFilter';
import { Button } from '../components/ui/button';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '../components/ui/card';
import {
  useReportingOptions,
  type Selection,
} from '../components/useReportingOptions';
import { toErrorMessage } from '../lib/errors';
import { useServices } from '../services/servicesContext';
import type { DashboardKpis } from '../services/types';

function windows(startDate: string, endDate: string) {
  const start = Date.parse(`${startDate}T00:00:00Z`);
  const end = Date.parse(`${endDate}T00:00:00Z`);
  const days = Math.floor((end - start) / 86400000) + 1;
  const count = Math.min(days, 3);
  return Array.from({ length: count }, (_, index) => {
    const iso = (day: number) =>
      new Date(start + day * 86400000).toISOString().slice(0, 10);
    return {
      startDate: iso(Math.floor((index * days) / count)),
      endDate: iso(Math.floor(((index + 1) * days) / count) - 1),
    };
  });
}

export function DashboardPage() {
  const { user, signOut } = useAuth();
  const services = useServices();
  const navigate = useNavigate();
  const [signingOut, setSigningOut] = useState(false);
  const { options, names, error: optionsError } = useReportingOptions();
  const [selected, setSelection] = useState<Selection>(options[0]);
  const [data, setData] = useState<DashboardKpis | null>(null);
  const [trend, setTrend] = useState<{ label: string; data: DashboardKpis }[]>(
    [],
  );
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const ranges = windows(selected.startDate, selected.endDate);
    Promise.all([
      services.reporting.dashboard(selected.filters),
      Promise.all(
        ranges.map(async (range) => ({
          label: `${range.startDate} – ${range.endDate}`,
          data: await services.reporting.dashboard(range),
        })),
      ),
    ])
      .then(([kpis, points]) => {
        if (active) {
          setData(kpis);
          setTrend(points);
          setLoading(false);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(toErrorMessage(reason));
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [services, selected]);

  async function handleSignOut() {
    setSigningOut(true);
    try {
      await services.auth.logout();
    } catch {
      /* Clear local session on failure. */
    } finally {
      signOut();
      setSigningOut(false);
      navigate('/login', { replace: true });
    }
  }

  const hasTrend = trend.some(
    ({ data: point }) =>
      point.currentCycleSpend !== 0 || point.revenueToDate !== 0,
  );
  return (
    <section className="page-section">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1>Dashboard</h1>
          <p>Signed in as {user?.email}</p>
          {user ? <p>Role: {user.role}</p> : null}
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={handleSignOut}
          disabled={signingOut}
        >
          {signingOut ? 'Signing out…' : 'Sign out'}
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle as="h2" className="text-base">
            Farm performance
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <ReportingFilter
            options={options}
            names={names}
            value={selected.key}
            onChange={(value) => {
              setLoading(true);
              setError('');
              setData(null);
              setSelection(value);
            }}
          />
          {optionsError && <p role="alert">{optionsError}</p>}
          {loading && <p>Loading dashboard…</p>}
          {error && <p role="alert">{error}</p>}
        </CardContent>
      </Card>

      {data && (
        <>
          <dl className="metric-grid">
            <Metric
              label="Current-cycle spend"
              value={data.currentCycleSpend}
            />
            <Metric label="Revenue to date" value={data.revenueToDate} />
            <Metric
              label="Upcoming activities"
              value={data.upcomingActivities}
            />
            <Metric label="Overdue activities" value={data.overdueActivities} />
            <Metric label="Low-stock count" value={data.lowStockItemCount} />
            <div className="metric-card">
              <dt>Unsold produce</dt>
              <dd className="mt-1 text-sm text-foreground">
                {data.unsoldProduce.length
                  ? data.unsoldProduce.map((item) => (
                      <div key={item.cycleId}>
                        Cycle {item.cycleId}: {item.quantity} (unit{' '}
                        {item.unitId})
                      </div>
                    ))
                  : 'None'}
              </dd>
            </div>
          </dl>

          {hasTrend ? (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle as="h2">Spend and revenue trend</CardTitle>
                  <p>Values are reported by the server for each sub-period.</p>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <table>
                      <thead>
                        <tr>
                          <th>Period</th>
                          <th>Spend</th>
                          <th>Revenue</th>
                        </tr>
                      </thead>
                      <tbody>
                        {trend.map((point) => (
                          <tr key={point.label}>
                            <th scope="row" className="text-foreground">
                              {point.label}
                            </th>
                            <td>{point.data.currentCycleSpend}</td>
                            <td>{point.data.revenueToDate}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle as="h2">Spend and revenue comparison</CardTitle>
                </CardHeader>
                <CardContent>
                  <BarChart
                    values={[
                      ['Spend', data.currentCycleSpend],
                      ['Revenue', data.revenueToDate],
                    ]}
                  />
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle as="h3">Trend chart</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  {trend.map((point) => (
                    <div key={point.label} className="space-y-2">
                      <h3>{point.label}</h3>
                      <BarChart
                        values={[
                          ['Spend', point.data.currentCycleSpend],
                          ['Revenue', point.data.revenueToDate],
                        ]}
                      />
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          ) : (
            <p>No spend or revenue data for this period.</p>
          )}
        </>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric-card">
      <dt>{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tracking-tight text-foreground">
        {value}
      </dd>
    </div>
  );
}

function BarChart({ values }: { values: [string, number][] }) {
  const max = Math.max(...values.map(([, value]) => Math.abs(value)), 1);
  return (
    <div
      className="space-y-3"
      role="img"
      aria-label={values
        .map(([label, value]) => `${label}: ${value}`)
        .join(', ')}
    >
      {values.map(([label, value]) => (
        <div key={label} className="space-y-1">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{label}</span>
            <span className="font-medium text-foreground">{value}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              aria-hidden="true"
              className="h-full rounded-full bg-primary"
              style={{ width: `${(Math.abs(value) / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
