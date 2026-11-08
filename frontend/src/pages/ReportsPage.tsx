import { useEffect, useState } from 'react';
import { ReportingFilter } from '../components/ReportingFilter';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import {
  useReportingOptions,
  type Selection,
} from '../components/useReportingOptions';
import { toErrorMessage } from '../lib/errors';
import { useServices } from '../services/servicesContext';
import type {
  ExportFormat,
  ReportName,
  ReportResult,
  ReportRow,
} from '../services/types';

const REPORTS: { name: ReportName; label: string }[] = [
  { name: 'activity-status', label: 'Activity status' },
  { name: 'inventory', label: 'Inventory' },
  { name: 'labour-usage', label: 'Labour usage' },
  { name: 'equipment-usage', label: 'Equipment usage' },
  { name: 'budget-vs-actual', label: 'Budget versus actual' },
];

export function ReportsPage() {
  const { reporting } = useServices();
  const { options, names, error: optionsError } = useReportingOptions();
  const [selection, setSelection] = useState<Selection | null>(null);
  const [name, setName] = useState<ReportName>('activity-status');
  const [applied, setApplied] = useState<{
    name: ReportName;
    selection: Selection;
  } | null>(null);
  const [result, setResult] = useState<ReportResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
  const selected = selection ?? options[0];

  useEffect(() => {
    if (!applied) return;
    let active = true;
    reporting
      .report(applied.name, applied.selection.filters)
      .then((value) => {
        if (active) {
          setResult(value);
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
  }, [applied, reporting]);

  async function download(format: ExportFormat) {
    if (!applied) return;
    setExporting(true);
    setError('');
    try {
      const blob = await reporting.exportReport(
        applied.name,
        applied.selection.filters,
        format,
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${applied.name}.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(toErrorMessage(reason));
    } finally {
      setExporting(false);
    }
  }

  return (
    <section className="page-section">
      <div className="space-y-1">
        <h1>Reports</h1>
        <p>Generate operational and financial reports for a period.</p>
      </div>

      <form
        className="page-form"
        onSubmit={(event) => {
          event.preventDefault();
          setResult(null);
          setError('');
          setLoading(true);
          setApplied({ name, selection: selected });
        }}
      >
        <div>
          <label htmlFor="report-name">Report</label>
          <select
            id="report-name"
            value={name}
            onChange={(event) => setName(event.target.value as ReportName)}
          >
            {REPORTS.map((report) => (
              <option key={report.name} value={report.name}>
                {report.label}
              </option>
            ))}
          </select>
        </div>
        <ReportingFilter
          options={options}
          names={names}
          value={selected.key}
          onChange={setSelection}
        />
        <Button type="submit">Apply filters</Button>
      </form>

      {optionsError && <p role="alert">{optionsError}</p>}
      {error && <p role="alert">{error}</p>}
      {loading && <p>Loading report…</p>}

      {result && applied && (
        <div className="space-y-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h2>
                {REPORTS.find((report) => report.name === applied.name)?.label}
              </h2>
              <p>
                {names[applied.selection.key] ?? 'Year to date'} (
                {applied.selection.startDate} – {applied.selection.endDate})
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {(['csv', 'xlsx', 'pdf'] as const).map((format) => (
                <Button
                  key={format}
                  type="button"
                  variant="outline"
                  disabled={exporting}
                  onClick={() => void download(format)}
                >
                  Export {format === 'xlsx' ? 'Excel' : format.toUpperCase()}
                </Button>
              ))}
            </div>
          </div>
          <ReportTables result={result} />
        </div>
      )}
    </section>
  );
}

function Table({ title, rows }: { title: string; rows: ReportRow[] }) {
  if (!rows.length)
    return <p>No {title.toLowerCase()} data for this period.</p>;
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  return (
    <Card>
      <CardHeader>
        <h3>{title}</h3>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index}>
                  {columns.map((column) => (
                    <td key={column}>
                      {row[column] == null ? '—' : String(row[column])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function ReportTables({ result }: { result: ReportResult }) {
  if ('counts' in result) {
    return result.total === 0 ? (
      <p>No activity data for this period.</p>
    ) : (
      <Table
        title="Activity status"
        rows={Object.entries(result.counts).map(([status, count]) => ({
          status,
          count,
        }))}
      />
    );
  }
  if ('items' in result)
    return (
      <>
        <p>As of {result.asOf}</p>
        <Table title="Inventory" rows={result.items} />
      </>
    );
  if ('rows' in result)
    return (
      <>
        <Table title="Usage" rows={result.rows} />
        {result.rows.length > 0 && (
          <Table title="Totals" rows={[result.totals]} />
        )}
      </>
    );
  return (
    <>
      <Table title="Overall budgets" rows={result.overall} />
      <Table title="Category budgets" rows={result.categories} />
    </>
  );
}
