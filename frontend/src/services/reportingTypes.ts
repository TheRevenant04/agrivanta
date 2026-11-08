import type {
  DashboardKpis as ApiDashboardKpis,
  ExportFormat as ApiExportFormat,
  ReportCell as ApiReportCell,
  ReportFilters as ApiReportFilters,
  ReportName as ApiReportName,
  ReportResult as ApiReportResult,
  ReportRow as ApiReportRow,
  ReportingPeriod as ApiReportingPeriod,
} from './generated/types.gen';

export type ReportingPeriod = ApiReportingPeriod;
export type ReportFilters = ApiReportFilters;
export type DashboardKpis = ApiDashboardKpis;
export type ReportName = ApiReportName;
export type ExportFormat = ApiExportFormat;
export type ReportCell = ApiReportCell;
export type ReportRow = ApiReportRow;
export type ReportResult = ApiReportResult;

export interface ReportingServices {
  reporting: {
    periods(): Promise<ReportingPeriod[]>;
    seasons(): Promise<ReportingPeriod[]>;
    dashboard(filters: ReportFilters): Promise<DashboardKpis>;
    report(name: ReportName, filters: ReportFilters): Promise<ReportResult>;
    exportReport(
      name: ReportName,
      filters: ReportFilters,
      format: ExportFormat,
    ): Promise<Blob>;
  };
}
