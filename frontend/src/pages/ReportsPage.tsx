import { useEffect, useState } from 'react';
import { ReportingFilter } from '../components/ReportingFilter';
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
    <section>
      <h1>Reports</h1>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setResult(null);
          setError('');
          setLoading(true);
          setApplied({ name, selection: selected });
        }}
      >
        <label>
          Report
          <select
            value={name}
            onChange={(event) => setName(event.target.value as ReportName)}
          >
            {REPORTS.map((report) => (
              <option key={report.name} value={report.name}>
                {report.label}
              </option>
            ))}
          </select>
        </label>
        <ReportingFilter
          options={options}
          names={names}
          value={selected.key}
          onChange={setSelection}
        />
        <button type="submit">Apply filters</button>
      </form>
      {optionsError && <p role="alert">{optionsError}</p>}
      {error && <p role="alert">{error}</p>}
      {loading && <p>Loading report…</p>}
      {result && applied && (
        <>
          <h2>
            {REPORTS.find((report) => report.name === applied.name)?.label}
          </h2>
          <p>
            {names[applied.selection.key] ?? 'Year to date'} (
            {applied.selection.startDate} – {applied.selection.endDate})
          </p>
          <ReportTables result={result} />
          {(['csv', 'xlsx', 'pdf'] as const).map((format) => (
            <button
              key={format}
              type="button"
              disabled={exporting}
              onClick={() => void download(format)}
            >
              Export {format === 'xlsx' ? 'Excel' : format.toUpperCase()}
            </button>
          ))}
        </>
      )}
    </section>
  );
}

function Table({ title, rows }: { title: string; rows: ReportRow[] }) {
  if (!rows.length)
    return <p>No {title.toLowerCase()} data for this period.</p>;
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  return (
    <section>
      <h3>{title}</h3>
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
    </section>
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
