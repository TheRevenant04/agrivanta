import { useState, type ChangeEvent } from 'react';
import { Button } from '../components/ui/button';
import { apiFieldError, toErrorMessage } from '../lib/errors';
import { useServices } from '../services/servicesContext';
import type {
  ImportEntityType,
  ImportPreview,
  ImportRowError,
  ImportValidRow,
} from '../services/types';

type ImportField =
  | 'date'
  | 'category'
  | 'amount'
  | 'supplier'
  | 'notes'
  | 'cycleId'
  | 'item'
  | 'type'
  | 'quantity'
  | 'note';

interface FieldDefinition {
  name: ImportField;
  label: string;
}

interface PreviewEntry {
  row: number;
  status: 'valid' | 'invalid' | 'duplicate';
  values: ImportValidRow;
  errors: ImportRowError[];
  duplicateReason?: string;
}

const FIELD_DEFINITIONS: Record<ImportEntityType, FieldDefinition[]> = {
  expenses: [
    { name: 'date', label: 'Date' },
    { name: 'category', label: 'Category' },
    { name: 'amount', label: 'Amount' },
    { name: 'supplier', label: 'Supplier' },
    { name: 'notes', label: 'Notes' },
    { name: 'cycleId', label: 'Crop cycle ID' },
  ],
  inventory_movements: [
    { name: 'item', label: 'Item' },
    { name: 'type', label: 'Type' },
    { name: 'quantity', label: 'Quantity' },
    { name: 'date', label: 'Date' },
    { name: 'note', label: 'Note' },
  ],
};

const EXPENSE_CATEGORIES = [
  'inputs',
  'labour',
  'equipment',
  'overhead',
  'other',
];
const MOVEMENT_TYPES = ['purchase', 'usage', 'adjustment'];

function isSupportedFile(file: File): boolean {
  return /\.(csv|xlsx)$/i.test(file.name);
}

function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  return (
    Number(value.slice(0, 4)) > 0 &&
    !Number.isNaN(parsed.valueOf()) &&
    parsed.toISOString().slice(0, 10) === value
  );
}

function validPositiveNumber(value: string): boolean {
  const text = value.trim();
  const parsed = Number(text);
  if (
    !text ||
    !Number.isFinite(parsed) ||
    parsed <= 0 ||
    parsed >= 10_000_000_000
  ) {
    return false;
  }
  const parts = text.match(/^([+-]?)(\d*)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/);
  if (!parts || !/\d/.test(text)) {
    return false;
  }
  const digits = `${parts[2]}${parts[3] ?? ''}`;
  const trailingZeros = digits.match(/0+$/)?.[0].length ?? 0;
  const normalizedScale =
    (parts[3] ?? '').length - Number(parts[4] ?? 0) - trailingZeros;
  return normalizedScale <= 4;
}

function correctionIsValid(
  field: string,
  value: string,
  entityType: ImportEntityType,
  itemNames: string[],
  cycleIds: string[],
): boolean {
  switch (field) {
    case 'date':
      return validDate(value);
    case 'category':
      return EXPENSE_CATEGORIES.includes(value);
    case 'amount':
    case 'quantity':
      return validPositiveNumber(value);
    case 'type':
      return MOVEMENT_TYPES.includes(value);
    case 'item':
      return (
        entityType === 'inventory_movements' &&
        itemNames.some((name) => name.toLowerCase() === value.toLowerCase())
      );
    case 'cycleId':
      return !value || cycleIds.includes(value);
    default:
      return false;
  }
}

function previewEntries(preview: ImportPreview): PreviewEntry[] {
  const valid = preview.validRows.map((row) => ({
    row: row.row,
    status: 'valid' as const,
    values: row,
    errors: [],
  }));
  const invalid = preview.invalidRows.map((row) => ({
    row: row.row,
    status: 'invalid' as const,
    values: { row: row.row },
    errors: row.errors,
  }));
  const duplicates = preview.duplicateRows.map((row) => ({
    row: row.row,
    status: 'duplicate' as const,
    values: { row: row.row, ...row.key } as ImportValidRow,
    errors: [],
    duplicateReason: row.reason,
  }));

  return [...valid, ...invalid, ...duplicates].sort((a, b) => a.row - b.row);
}

export function ImportWizardPage() {
  const services = useServices();
  const [entityType, setEntityType] = useState<ImportEntityType>('expenses');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [itemNames, setItemNames] = useState<string[]>([]);
  const [cycleIds, setCycleIds] = useState<string[]>([]);
  const [corrections, setCorrections] = useState<
    Record<number, Record<string, string>>
  >({});
  const [skippedRows, setSkippedRows] = useState<Set<number>>(new Set());
  const [selectedRows, setSelectedRows] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [importedCount, setImportedCount] = useState<number | null>(null);

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const chosen = event.currentTarget.files?.[0] ?? null;
    setFile(chosen);
    setPreview(null);
    setCorrections({});
    setSkippedRows(new Set());
    setSelectedRows(new Set());
    setImportedCount(null);
    setError(
      chosen && !isSupportedFile(chosen)
        ? 'Unsupported file type. Choose a .csv or .xlsx file.'
        : null,
    );
  }

  async function uploadFile() {
    if (!file) {
      setError('Choose a file to continue.');
      return;
    }
    if (!isSupportedFile(file)) {
      setError('Unsupported file type. Choose a .csv or .xlsx file.');
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      if (entityType === 'inventory_movements') {
        const items = await services.items.list();
        setItemNames(items.map((item) => item.name));
        setCycleIds([]);
      } else {
        setItemNames([]);
        const cycles = await services.cropCycles.list();
        setCycleIds(cycles.map((cycle) => cycle.id));
      }

      const result = await services.imports.preview(entityType, file);
      setPreview(result);
      setCorrections({});
      setSkippedRows(new Set());
      setSelectedRows(new Set(result.validRows.map((row) => row.row)));
    } catch (cause) {
      setError(toErrorMessage(cause));
    } finally {
      setSubmitting(false);
    }
  }

  function currentErrors(
    entry: PreviewEntry,
    values: Record<string, string> = corrections[entry.row] ?? {},
  ): ImportRowError[] {
    return entry.errors.filter(
      ({ field }) =>
        !correctionIsValid(
          field,
          values[field] ?? '',
          entityType,
          itemNames,
          cycleIds,
        ),
    );
  }

  function editCorrection(entry: PreviewEntry, field: string, value: string) {
    const updated = {
      ...(corrections[entry.row] ?? {}),
      [field]: value,
    };
    setCorrections((existing) => ({ ...existing, [entry.row]: updated }));
    const unresolved = entry.errors.some(
      (rowError) =>
        !correctionIsValid(
          rowError.field,
          updated[rowError.field] ?? '',
          entityType,
          itemNames,
          cycleIds,
        ),
    );
    setSelectedRows((existing) => {
      const next = new Set(existing);
      if (unresolved || skippedRows.has(entry.row)) {
        next.delete(entry.row);
      } else {
        next.add(entry.row);
      }
      return next;
    });
  }

  function toggleRow(rowNumber: number) {
    setSelectedRows((existing) => {
      const next = new Set(existing);
      if (next.has(rowNumber)) {
        next.delete(rowNumber);
      } else {
        next.add(rowNumber);
      }
      return next;
    });
  }

  function cancelPreview() {
    setPreview(null);
    setFile(null);
    setCorrections({});
    setSkippedRows(new Set());
    setSelectedRows(new Set());
    setError(null);
  }

  async function confirmImport() {
    if (!preview) {
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const result = await services.imports.commit({
        token: preview.previewToken,
        confirmedRows: [...selectedRows]
          .filter((row) => !skippedRows.has(row))
          .sort((a, b) => a - b)
          .map((row) => ({
            row,
            ...(corrections[row] ? { values: corrections[row] } : {}),
          })),
      });
      setImportedCount(result.counts.imported);
      setPreview(null);
    } catch (cause) {
      const { message } = apiFieldError(cause);
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  const entries = preview ? previewEntries(preview) : [];
  const hasInvalidRows = entries.some(
    (entry) => currentErrors(entry).length > 0 && !skippedRows.has(entry.row),
  );
  const columns = FIELD_DEFINITIONS[entityType];

  return (
    <section className="page-section import-wizard">
      <div className="space-y-1">
        <h1>Import records</h1>
        <p>Upload a CSV or Excel file, review rows, then confirm the import.</p>
      </div>

      {importedCount !== null ? (
        <div className="import-success" role="status">
          <h2>Import complete</h2>
          <p>
            Successfully imported {importedCount}{' '}
            {importedCount === 1 ? 'row' : 'rows'}.
          </p>
          <Button
            type="button"
            onClick={() => {
              setImportedCount(null);
              setFile(null);
              setError(null);
            }}
          >
            Import another file
          </Button>
        </div>
      ) : null}

      {importedCount === null && !preview ? (
        <div className="page-form">
          <h2>Step 1: Choose a file</h2>
          <label>
            Records to import
            <select
              value={entityType}
              onChange={(event) =>
                setEntityType(event.currentTarget.value as ImportEntityType)
              }
            >
              <option value="expenses">Expenses</option>
              <option value="inventory_movements">Inventory movements</option>
            </select>
          </label>
          <label>
            CSV or Excel file
            <input type="file" accept=".csv,.xlsx" onChange={chooseFile} />
          </label>
          {file ? <p>Selected file: {file.name}</p> : null}
          {error ? <p role="alert">{error}</p> : null}
          <Button
            type="button"
            onClick={uploadFile}
            disabled={
              !file || submitting || Boolean(file && !isSupportedFile(file))
            }
          >
            {submitting ? 'Uploading…' : 'Upload and preview'}
          </Button>
        </div>
      ) : null}

      {preview && importedCount === null ? (
        <div className="page-form">
          <h2>Step 2: Review and confirm</h2>
          <p>File: {preview.fileName}</p>
          <p>
            {preview.counts.total} rows · {preview.counts.valid} valid ·{' '}
            {preview.counts.invalid} invalid · {preview.counts.duplicate}{' '}
            duplicates
          </p>
          {error ? <p role="alert">{error}</p> : null}
          <div className="import-table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">Import</th>
                  <th scope="col">Source row</th>
                  {columns.map(({ name, label }) => (
                    <th key={name} scope="col">
                      {label}
                    </th>
                  ))}
                  <th scope="col">Review</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => {
                  const remainingErrors = currentErrors(entry);
                  return (
                    <tr
                      key={entry.row}
                      className={
                        skippedRows.has(entry.row)
                          ? 'import-row-skipped'
                          : remainingErrors.length
                            ? 'import-row-invalid'
                            : entry.status === 'duplicate'
                              ? 'import-row-duplicate'
                              : ''
                      }
                    >
                      <td>
                        {entry.status === 'duplicate' ||
                        skippedRows.has(entry.row) ? (
                          '—'
                        ) : (
                          <input
                            type="checkbox"
                            aria-label={`Import row ${entry.row}`}
                            checked={selectedRows.has(entry.row)}
                            disabled={remainingErrors.length > 0}
                            onChange={() => toggleRow(entry.row)}
                          />
                        )}
                      </td>
                      <th scope="row">{entry.row}</th>
                      {columns.map(({ name, label }) => {
                        const rowError = entry.errors.find(
                          (candidate) => candidate.field === name,
                        );
                        const unresolvedError =
                          rowError && remainingErrors.includes(rowError);
                        const correction = corrections[entry.row]?.[name];

                        return (
                          <td key={name}>
                            {rowError ? (
                              <label className="import-correction">
                                <span className="visually-hidden">
                                  Correct {label} for row {entry.row}
                                </span>
                                {name === 'category' ||
                                name === 'type' ||
                                name === 'item' ? (
                                  <select
                                    aria-label={`Correct ${label} for row ${entry.row}`}
                                    aria-invalid={Boolean(unresolvedError)}
                                    value={correction ?? ''}
                                    onChange={(event) =>
                                      editCorrection(
                                        entry,
                                        name,
                                        event.currentTarget.value,
                                      )
                                    }
                                  >
                                    <option value="">
                                      Select {label.toLowerCase()}
                                    </option>
                                    {(name === 'category'
                                      ? EXPENSE_CATEGORIES
                                      : name === 'type'
                                        ? MOVEMENT_TYPES
                                        : itemNames
                                    ).map((option) => (
                                      <option key={option} value={option}>
                                        {option}
                                      </option>
                                    ))}
                                  </select>
                                ) : (
                                  <input
                                    aria-label={`Correct ${label} for row ${entry.row}`}
                                    aria-invalid={Boolean(unresolvedError)}
                                    type={name === 'date' ? 'date' : 'text'}
                                    inputMode={
                                      name === 'amount' || name === 'quantity'
                                        ? 'decimal'
                                        : undefined
                                    }
                                    value={correction ?? ''}
                                    onChange={(event) =>
                                      editCorrection(
                                        entry,
                                        name,
                                        event.currentTarget.value,
                                      )
                                    }
                                  />
                                )}
                                {unresolvedError ? (
                                  <span className="import-row-error">
                                    {rowError?.message}
                                  </span>
                                ) : null}
                              </label>
                            ) : (entry.values[name] ??
                                (name === 'item'
                                  ? entry.values.itemId
                                  : undefined)) == null ||
                              (entry.values[name] ??
                                (name === 'item'
                                  ? entry.values.itemId
                                  : undefined)) === '' ? (
                              '—'
                            ) : (
                              String(
                                entry.values[name] ??
                                  (name === 'item'
                                    ? entry.values.itemId
                                    : undefined),
                              )
                            )}
                          </td>
                        );
                      })}
                      <td>
                        {entry.status === 'duplicate' ? (
                          <span className="import-duplicate">
                            Duplicate: {entry.duplicateReason}
                          </span>
                        ) : skippedRows.has(entry.row) ? (
                          <div>
                            <p role="status">
                              This invalid row will be skipped and not imported.
                            </p>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() =>
                                setSkippedRows((existing) => {
                                  const next = new Set(existing);
                                  next.delete(entry.row);
                                  return next;
                                })
                              }
                            >
                              Undo skip row {entry.row}
                            </Button>
                          </div>
                        ) : remainingErrors.length ? (
                          <>
                            <ul className="import-errors">
                              {remainingErrors
                                .filter(
                                  ({ field }) =>
                                    !columns.some(
                                      (column) => column.name === field,
                                    ),
                                )
                                .map(({ field, message }, index) => (
                                  <li key={`${field}-${index}`}>
                                    {field}: {message}
                                  </li>
                                ))}
                            </ul>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setSkippedRows((existing) =>
                                  new Set(existing).add(entry.row),
                                );
                                setSelectedRows((existing) => {
                                  const next = new Set(existing);
                                  next.delete(entry.row);
                                  return next;
                                });
                              }}
                            >
                              Skip invalid row {entry.row}
                            </Button>
                          </>
                        ) : entry.status === 'invalid' ? (
                          'Corrected'
                        ) : (
                          'Ready'
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="import-actions">
            <Button
              type="button"
              variant="outline"
              onClick={cancelPreview}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={confirmImport}
              disabled={submitting || hasInvalidRows || selectedRows.size === 0}
            >
              {submitting
                ? 'Importing…'
                : `Confirm import (${selectedRows.size} selected)`}
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
