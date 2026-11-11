import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '@/App';
import { createMockServices, MOCK_USERS } from '@/services/mockServices';
import { createMemorySessionStore } from '@/services/sessionStore';
import { ApiError } from '@/services/types';
import type {
  DashboardKpis,
  ReportName,
  ReportResult,
} from '@/services/types';

const period = {
  id: 'p1',
  name: 'Spring',
  startDate: '2025-01-01',
  endDate: '2025-03-31',
};
const season = {
  id: 's1',
  name: 'Summer',
  startDate: '2025-04-01',
  endDate: '2025-06-30',
};
const kpis: DashboardKpis = {
  currentCycleSpend: 120,
  revenueToDate: 300,
  unsoldProduce: [{ cycleId: 'c1', quantity: 5, unitId: 'kg' }],
  upcomingActivities: 2,
  overdueActivities: 1,
  lowStockItemCount: 3,
};

async function setup(route: string) {
  const store = createMemorySessionStore();
  const services = createMockServices({ store });
  await services.auth.login({
    email: MOCK_USERS[0].email,
    password: MOCK_USERS[0].password,
  });
  services.reporting.periods = vi.fn().mockResolvedValue([period]);
  services.reporting.seasons = vi.fn().mockResolvedValue([season]);
  services.reporting.dashboard = vi.fn().mockResolvedValue(kpis);
  services.reporting.report = vi
    .fn()
    .mockResolvedValue({ counts: {}, total: 0 });
  services.reporting.exportReport = vi
    .fn()
    .mockResolvedValue(new Blob(['test']));
  window.history.pushState({}, '', route);
  render(<App services={services} store={store} />);
  await screen.findByRole('option', { name: 'Period: Spring' });
  return services;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('dashboard and reports', () => {
  it('refetches KPI and trend data when the period or season changes', async () => {
    const services = await setup('/dashboard');
    expect((await screen.findAllByText('300')).length).toBeGreaterThan(0);
    expect(screen.getByText('Cycle c1: 5 (unit kg)')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Spend and revenue trend' }),
    ).toBeInTheDocument();
    vi.mocked(services.reporting.dashboard).mockClear();
    vi.mocked(services.reporting.dashboard).mockResolvedValue({
      ...kpis,
      revenueToDate: 42,
    });
    fireEvent.change(screen.getByLabelText('Period or season'), {
      target: { value: 'period:p1' },
    });
    await waitFor(() =>
      expect(services.reporting.dashboard).toHaveBeenCalledWith({
        periodId: 'p1',
      }),
    );
    await waitFor(() =>
      expect(screen.getAllByText('42').length).toBeGreaterThan(0),
    );
    fireEvent.change(screen.getByLabelText('Period or season'), {
      target: { value: 'season:s1' },
    });
    await waitFor(() =>
      expect(services.reporting.dashboard).toHaveBeenCalledWith({
        startDate: '2025-04-01',
        endDate: '2025-06-30',
      }),
    );
  });

  it('renders an empty chart state for a period with no spend or revenue', async () => {
    const services = await setup('/dashboard');
    await screen.findAllByText('300');
    vi.mocked(services.reporting.dashboard).mockResolvedValue({
      ...kpis,
      currentCycleSpend: 0,
      revenueToDate: 0,
    });
    fireEvent.change(screen.getByLabelText('Period or season'), {
      target: { value: 'period:p1' },
    });
    expect(
      await screen.findByText('No spend or revenue data for this period.'),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Trend chart' }),
    ).not.toBeInTheDocument();
  });

  it.each([
    ['activity-status', { counts: { completed: 7 }, total: 7 }, 'completed'],
    [
      'inventory',
      {
        asOf: '2025-03-31',
        items: [{ name: 'Fertilizer', currentQuantity: 9 }],
      },
      'Fertilizer',
    ],
    [
      'labour-usage',
      {
        groupBy: 'cycle',
        rows: [{ workerName: 'Ada', hours: 2, cost: 50 }],
        totals: { hours: 2, cost: 50 },
      },
      'Ada',
    ],
    [
      'equipment-usage',
      {
        groupBy: 'cycle',
        rows: [{ equipmentName: 'Tractor', hours: 2, cost: 50 }],
        totals: { hours: 2, cost: 50 },
      },
      'Tractor',
    ],
  ] as [ReportName, ReportResult, string][])(
    'renders the %s report',
    async (name, payload, expected) => {
      const services = await setup('/reports');
      vi.mocked(services.reporting.report).mockResolvedValue(payload);
      fireEvent.change(screen.getByLabelText('Report'), {
        target: { value: name },
      });
      fireEvent.change(screen.getByLabelText('Period or season'), {
        target: { value: 'season:s1' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }));
      expect(await screen.findByText(expected)).toBeInTheDocument();
      expect(services.reporting.report).toHaveBeenCalledWith(name, {
        startDate: '2025-04-01',
        endDate: '2025-06-30',
      });
    },
  );

  it('displays report request failures', async () => {
    const services = await setup('/reports');
    vi.mocked(services.reporting.report).mockRejectedValue(
      new ApiError('Report unavailable', 500),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Report unavailable',
    );
    expect(
      screen.queryByRole('button', { name: 'Export CSV' }),
    ).not.toBeInTheDocument();
  });

  it('applies report filters and downloads every format for the displayed result', async () => {
    const services = await setup('/reports');
    vi.mocked(services.reporting.report).mockResolvedValue({
      overall: [{ budget: 100, actual: 120, variance: 20 }],
      categories: [],
    });
    const createUrl = vi.fn().mockReturnValue('blob:report');
    const revokeUrl = vi.fn();
    vi.stubGlobal(
      'URL',
      Object.assign(URL, {
        createObjectURL: createUrl,
        revokeObjectURL: revokeUrl,
      }),
    );
    const downloads: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloads.push(this.download);
    });
    expect(
      within(screen.getByLabelText('Report')).getAllByRole('option'),
    ).toHaveLength(5);
    fireEvent.change(screen.getByLabelText('Report'), {
      target: { value: 'budget-vs-actual' },
    });
    fireEvent.change(screen.getByLabelText('Period or season'), {
      target: { value: 'period:p1' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }));
    expect(await screen.findByText('120')).toBeInTheDocument();
    expect(services.reporting.report).toHaveBeenCalledWith('budget-vs-actual', {
      periodId: 'p1',
    });
    for (const [label, format] of [
      ['CSV', 'csv'],
      ['Excel', 'xlsx'],
      ['PDF', 'pdf'],
    ] as const) {
      fireEvent.click(screen.getByRole('button', { name: `Export ${label}` }));
      await waitFor(() =>
        expect(services.reporting.exportReport).toHaveBeenCalledWith(
          'budget-vs-actual',
          { periodId: 'p1' },
          format,
        ),
      );
      await waitFor(() =>
        expect(downloads).toContain(`budget-vs-actual.${format}`),
      );
    }
    expect(revokeUrl).toHaveBeenCalledTimes(3);
  });
});
