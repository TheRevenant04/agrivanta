import type { ServiceRequest } from './farmSetupHttp';
import type {
  DashboardKpis,
  ExportFormat,
  ReportFilters,
  ReportResult,
  ReportingPeriod,
  ReportingServices,
} from './reportingTypes';

type DownloadRequest = (path: string) => Promise<Blob>;

function query(filters: ReportFilters, format?: ExportFormat): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  if (format) params.set('exportFormat', format);
  const result = params.toString();
  return result ? `?${result}` : '';
}

export function createReportingHttp(
  request: ServiceRequest,
  download: DownloadRequest,
): ReportingServices {
  return {
    reporting: {
      periods: () =>
        request<ReportingPeriod[]>(
          '/reporting-periods',
          { method: 'GET' },
          true,
        ),
      seasons: () =>
        request<ReportingPeriod[]>('/seasons', { method: 'GET' }, true),
      dashboard: (filters) =>
        request<DashboardKpis>(
          `/dashboard${query(filters)}`,
          { method: 'GET' },
          true,
        ),
      report: (name, filters) =>
        request<ReportResult>(
          `/reports/${name}${query(filters)}`,
          { method: 'GET' },
          true,
        ),
      exportReport: (name, filters, format) =>
        download(`/reports/${name}/export${query(filters, format)}`),
    },
  };
}
