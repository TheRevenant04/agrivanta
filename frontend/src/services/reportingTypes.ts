export interface ReportingPeriod {
  id: string;
  name: string;
  startDate: string;
  endDate: string;
}

export interface ReportFilters {
  periodId?: string;
  startDate?: string;
  endDate?: string;
}

export interface DashboardKpis {
  currentCycleSpend: number;
  revenueToDate: number;
  unsoldProduce: { cycleId: string; quantity: number; unitId: string }[];
  upcomingActivities: number;
  overdueActivities: number;
  lowStockItemCount: number;
}

export type ReportName =
  | 'activity-status'
  | 'inventory'
  | 'labour-usage'
  | 'equipment-usage'
  | 'budget-vs-actual';
export type ExportFormat = 'csv' | 'xlsx' | 'pdf';
export type ReportCell = string | number | boolean | null;
export type ReportRow = Record<string, ReportCell>;
export type ReportResult =
  | { counts: Record<string, number>; total: number }
  | { asOf: string; items: ReportRow[] }
  | { groupBy: string; rows: ReportRow[]; totals: Record<string, number> }
  | { overall: ReportRow[]; categories: ReportRow[] };

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
