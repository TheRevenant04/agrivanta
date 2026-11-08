import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ImportWizardPage } from './ImportWizardPage';
import { createMemorySessionStore } from '../services/sessionStore';
import { createMockServices } from '../services/mockServices';
import { ServicesContext } from '../services/servicesContext';
import type { ImportCommitResult, ImportPreview } from '../services/types';
import { ApiError } from '../services/types';

const previewFixture: ImportPreview = {
  entityType: 'expenses',
  fileName: 'expenses.csv',
  previewToken: 'preview-token',
  expiresAt: '2026-03-01T00:00:00Z',
  totalRows: 3,
  validRows: [
    {
      row: 2,
      date: '2026-03-01',
      category: 'inputs',
      amount: 10,
      supplier: 'Farm Supply',
      notes: null,
      cycleId: null,
    },
  ],
  invalidRows: [
    {
      row: 3,
      errors: [{ field: 'amount', message: 'Amount must be a number.' }],
    },
  ],
  duplicateRows: [
    {
      row: 4,
      reason: 'Duplicate of an existing expense.',
      key: {
        date: '2026-03-01',
        category: 'inputs',
        amount: 10,
        supplier: 'Farm Supply',
      },
    },
  ],
  counts: { total: 3, valid: 1, invalid: 1, duplicate: 1 },
};

const commitFixture: ImportCommitResult = {
  previewToken: 'preview-token',
  entityType: 'expenses',
  imported: [{ row: 2, id: 'expense-1' }],
  counts: { confirmed: 1, imported: 1, skipped: 2 },
  audit: {
    id: 'audit-1',
    actorId: 'user-1',
    committedAt: '2026-03-01T00:00:00Z',
    entityCounts: { expenses: 1 },
    previewToken: 'preview-token',
  },
};

async function setup() {
  const store = createMemorySessionStore();
  const services = createMockServices({ store });
  await services.auth.login({
    email: 'owner@agrivanta.test',
    password: 'password123',
  });
  const preview = vi.fn(async (): Promise<ImportPreview> => previewFixture);
  const commit = vi.fn(async (): Promise<ImportCommitResult> => commitFixture);
  services.imports = { preview, commit };

  render(
    <ServicesContext.Provider value={services}>
      <ImportWizardPage />
    </ServicesContext.Provider>,
  );

  return { services, preview, commit };
}

function chooseCsv() {
  fireEvent.change(screen.getByLabelText('CSV or Excel file'), {
    target: {
      files: [new File(['contents'], 'expenses.csv', { type: 'text/csv' })],
    },
  });
}

async function uploadCsv(preview: ReturnType<typeof vi.fn>) {
  chooseCsv();
  expect(screen.getByText('Selected file: expenses.csv')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Upload and preview' }));
  await waitFor(() => expect(preview).toHaveBeenCalledOnce());
}

describe('ImportWizardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows backend row errors verbatim, highlights invalid rows, and disables confirm until corrected', async () => {
    const { preview } = await setup();
    await uploadCsv(preview);

    expect(
      await screen.findByText('Amount must be a number.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Duplicate: Duplicate of an existing expense.'),
    ).toBeInTheDocument();
    const invalidRow = screen
      .getAllByRole('row')
      .find((row) => row.querySelector('th')?.textContent === '3');
    expect(invalidRow).toBeDefined();
    expect(invalidRow).toHaveClass('import-row-invalid');
    const confirm = screen.getByRole('button', {
      name: 'Confirm import (1 selected)',
    });
    expect(confirm).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Correct Amount for row 3'), {
      target: { value: '20' },
    });

    expect(
      screen.queryByText('Amount must be a number.'),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText('Correct Amount for row 3')).toHaveValue('20');
    expect(invalidRow).not.toHaveClass('import-row-invalid');
    expect(
      screen.getByRole('button', { name: 'Confirm import (2 selected)' }),
    ).toBeEnabled();
  });

  it('commits only after explicit confirmation and reports the imported count', async () => {
    const { preview, commit } = await setup();
    await uploadCsv(preview);

    expect(commit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Import row 2' }));
    fireEvent.change(screen.getByLabelText('Correct Amount for row 3'), {
      target: { value: '20' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'Confirm import (1 selected)' }),
    );

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Successfully imported 1 row.',
    );
    expect(commit).toHaveBeenCalledWith({
      token: 'preview-token',
      confirmedRows: [{ row: 3, values: { amount: '20' } }],
    });
  });

  it('cancels a preview without committing any rows', async () => {
    const { preview, commit } = await setup();
    await uploadCsv(preview);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(commit).not.toHaveBeenCalled();
    expect(
      screen.getByRole('heading', { name: 'Step 1: Choose a file' }),
    ).toBeInTheDocument();
  });

  it('rejects unsupported files without uploading them', async () => {
    const { preview } = await setup();
    fireEvent.change(screen.getByLabelText('CSV or Excel file'), {
      target: { files: [new File(['contents'], 'expenses.xls')] },
    });

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Unsupported file type. Choose a .csv or .xlsx file.',
    );
    expect(preview).not.toHaveBeenCalled();
    expect(
      screen.getByRole('button', { name: 'Upload and preview' }),
    ).toBeDisabled();
  });

  it('accepts an Excel file and sends it to the preview service', async () => {
    const { preview } = await setup();
    const file = new File(['workbook'], 'expenses.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    fireEvent.change(screen.getByLabelText('CSV or Excel file'), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Upload and preview' }));

    await waitFor(() => {
      expect(preview).toHaveBeenCalledWith('expenses', file);
    });
  });

  it('keeps unreadable uploads on step 1 and shows the backend error', async () => {
    const { preview } = await setup();
    preview.mockRejectedValueOnce(
      new ApiError('The CSV file could not be parsed.', 400, 'file'),
    );
    chooseCsv();
    fireEvent.click(screen.getByRole('button', { name: 'Upload and preview' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The CSV file could not be parsed.',
    );
    expect(
      screen.getByRole('heading', { name: 'Step 1: Choose a file' }),
    ).toBeInTheDocument();
  });
});
