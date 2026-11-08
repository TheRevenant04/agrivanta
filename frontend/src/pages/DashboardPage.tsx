import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/authContext';
import { ReportingFilter } from '../components/ReportingFilter';
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
    <section>
      <h1>Dashboard</h1>
      <p>Signed in as {user?.email}</p>
      {user ? <p>Role: {user.role}</p> : null}
      <button type="button" onClick={handleSignOut} disabled={signingOut}>
        {signingOut ? 'Signing out…' : 'Sign out'}
      </button>
      <h2>Farm performance</h2>
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
      {data && (
        <>
          <dl>
            <dt>Current-cycle spend</dt>
            <dd>{data.currentCycleSpend}</dd>
            <dt>Revenue to date</dt>
            <dd>{data.revenueToDate}</dd>
            <dt>Unsold produce</dt>
            <dd>
              {data.unsoldProduce.length
                ? data.unsoldProduce.map((item) => (
                    <div key={item.cycleId}>
                      Cycle {item.cycleId}: {item.quantity} (unit {item.unitId})
                    </div>
                  ))
                : 'None'}
            </dd>
            <dt>Upcoming activities</dt>
            <dd>{data.upcomingActivities}</dd>
            <dt>Overdue activities</dt>
            <dd>{data.overdueActivities}</dd>
            <dt>Low-stock count</dt>
            <dd>{data.lowStockItemCount}</dd>
          </dl>
          {hasTrend ? (
            <>
              <h2>Spend and revenue trend</h2>
              <p>Values are reported by the server for each sub-period.</p>
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
                      <th>{point.label}</th>
                      <td>{point.data.currentCycleSpend}</td>
                      <td>{point.data.revenueToDate}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h2>Spend and revenue comparison</h2>
              <BarChart
                values={[
                  ['Spend', data.currentCycleSpend],
                  ['Revenue', data.revenueToDate],
                ]}
              />
              <h3>Trend chart</h3>
              {trend.map((point) => (
                <div key={point.label}>
                  <h4>{point.label}</h4>
                  <BarChart
                    values={[
                      ['Spend', point.data.currentCycleSpend],
                      ['Revenue', point.data.revenueToDate],
                    ]}
                  />
                </div>
              ))}
            </>
          ) : (
            <p>No spend or revenue data for this period.</p>
          )}
        </>
      )}
    </section>
  );
}

function BarChart({ values }: { values: [string, number][] }) {
  const max = Math.max(...values.map(([, value]) => Math.abs(value)), 1);
  return (
    <div
      role="img"
      aria-label={values
        .map(([label, value]) => `${label}: ${value}`)
        .join(', ')}
    >
      {values.map(([label, value]) => (
        <div key={label}>
          {label}: {value}
          <div
            aria-hidden="true"
            style={{
              background: '#367a40',
              height: '1em',
              width: `${(Math.abs(value) / max) * 100}%`,
            }}
          />
        </div>
      ))}
    </div>
  );
}
