import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderExpensesScreen } from '../testUtils/renderExpenses';
import type { Expense } from '../services/types';

function draftExpense(overrides: Partial<Expense> = {}): Expense {
  return {
    id: 'expense-1',
    category: 'inputs',
    amount: 120,
    date: '2026-01-01',
    supplier: 'Acme',
    status: 'draft',
    attachments: [],
    ...overrides,
  };
}

describe('ExpensesPage', () => {
  it('shows an empty state with a create action when there are no expenses', async () => {
    await renderExpensesScreen({ route: '/expenses' });

    expect(await screen.findByText('No expenses yet.')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Add expense' }),
    ).toBeInTheDocument();
  });

  it('offers every backend category and an optional supplier in the form', async () => {
    await renderExpensesScreen({ route: '/expenses' });

    fireEvent.click(await screen.findByRole('button', { name: 'Add expense' }));

    const category = screen.getByLabelText('Category') as HTMLSelectElement;

    expect(Array.from(category.options).map((option) => option.value)).toEqual([
      'inputs',
      'labour',
      'equipment',
      'overhead',
      'other',
    ]);

    expect(screen.getByLabelText('Supplier (optional)')).toBeInTheDocument();
  });

  it('saves a draft expense and shows the draft badge with edit and delete', async () => {
    const { services } = await renderExpensesScreen({ route: '/expenses' });

    fireEvent.click(await screen.findByRole('button', { name: 'Add expense' }));
    fireEvent.change(screen.getByLabelText('Category'), {
      target: { value: 'labour' },
    });
    fireEvent.change(screen.getByLabelText('Amount'), {
      target: { value: '250' },
    });
    fireEvent.change(screen.getByLabelText('Date'), {
      target: { value: '2026-01-15' },
    });
    fireEvent.change(screen.getByLabelText('Supplier (optional)'), {
      target: { value: 'Acme' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save expense' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Expense saved.',
    );
    expect(screen.getByText('draft')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Edit expense expense-1' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Delete expense expense-1' }),
    ).toBeInTheDocument();

    await expect(services.expenses.list()).resolves.toEqual([
      expect.objectContaining({
        category: 'labour',
        amount: 250,
        date: '2026-01-15',
        supplier: 'Acme',
        status: 'draft',
      }),
    ]);
  });

  it('shows the uploaded receipt file name on the saved expense', async () => {
    await renderExpensesScreen({ route: '/expenses' });

    fireEvent.click(await screen.findByRole('button', { name: 'Add expense' }));
    fireEvent.change(screen.getByLabelText('Amount'), {
      target: { value: '10' },
    });
    fireEvent.change(screen.getByLabelText('Date'), {
      target: { value: '2026-01-16' },
    });

    const file = new File(['receipt'], 'receipt-january.pdf', {
      type: 'application/pdf',
    });
    fireEvent.change(screen.getByLabelText('Receipt attachment'), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save expense' }));

    expect(await screen.findByText('receipt-january.pdf')).toBeInTheDocument();
  });

  it('flips the badge to posted when the expense is posted', async () => {
    await renderExpensesScreen({
      route: '/expenses',
      seed: { expenses: [draftExpense()] },
    });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Post expense expense-1' }),
    );

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Expense posted.',
    );
    await waitFor(() => {
      expect(screen.getByText('posted')).toBeInTheDocument();
    });
    expect(screen.queryByText('draft')).not.toBeInTheDocument();
  });

  it('hides edit and delete controls on a posted expense', async () => {
    await renderExpensesScreen({
      route: '/expenses',
      seed: { expenses: [draftExpense({ status: 'posted' })] },
    });

    expect(await screen.findByText('posted')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Edit expense expense-1' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Delete expense expense-1' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Post expense expense-1' }),
    ).not.toBeInTheDocument();
  });

  it('surfaces the backend error when a posted expense edit is rejected', async () => {
    // The list still shows a draft, but the record was posted elsewhere, so
    // the backend rejects the edit and the error must reach the user.
    const { services } = await renderExpensesScreen({
      route: '/expenses',
      seed: { expenses: [draftExpense()] },
    });

    await services.expenses.post('expense-1');

    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit expense expense-1' }),
    );
    fireEvent.change(screen.getByLabelText('Amount'), {
      target: { value: '999' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save expense' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Cannot edit a posted expense.');
  });

  it('deletes a draft expense', async () => {
    const { services } = await renderExpensesScreen({
      route: '/expenses',
      seed: { expenses: [draftExpense()] },
    });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Delete expense expense-1' }),
    );

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Expense deleted.',
    );
    expect(await screen.findByText('No expenses yet.')).toBeInTheDocument();
    await expect(services.expenses.list()).resolves.toEqual([]);
  });

  it('shows an inline error for a missing amount and saves nothing', async () => {
    const { services } = await renderExpensesScreen({ route: '/expenses' });

    fireEvent.click(await screen.findByRole('button', { name: 'Add expense' }));
    fireEvent.change(screen.getByLabelText('Date'), {
      target: { value: '2026-01-17' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save expense' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Amount is required.');
    expect(alert).toHaveAttribute('id', 'expense-amount-error');
    expect(screen.getByLabelText('Amount')).toHaveAttribute(
      'aria-invalid',
      'true',
    );

    await expect(services.expenses.list()).resolves.toEqual([]);
  });

  it('shows an inline error for a missing date and saves nothing', async () => {
    const { services } = await renderExpensesScreen({ route: '/expenses' });

    fireEvent.click(await screen.findByRole('button', { name: 'Add expense' }));
    fireEvent.change(screen.getByLabelText('Amount'), {
      target: { value: '42' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save expense' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Date is required.');
    expect(alert).toHaveAttribute('id', 'expense-date-error');

    await expect(services.expenses.list()).resolves.toEqual([]);
  });

  it('shows an inline error and saves nothing when an edited amount is cleared', async () => {
    const { services } = await renderExpensesScreen({
      route: '/expenses',
      seed: { expenses: [draftExpense()] },
    });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit expense expense-1' }),
    );
    fireEvent.change(screen.getByLabelText('Category'), {
      target: { value: 'labour' },
    });
    fireEvent.change(screen.getByLabelText('Amount'), {
      target: { value: '' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save expense' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Amount is required.');
    expect(alert).toHaveAttribute('id', 'expense-amount-error');

    // The rejected edit must not have applied the category it changed.
    await expect(services.expenses.list()).resolves.toEqual([
      expect.objectContaining({
        id: 'expense-1',
        category: 'inputs',
        amount: 120,
        date: '2026-01-01',
        supplier: 'Acme',
        status: 'draft',
      }),
    ]);
  });

  it('shows an inline error and saves nothing when an edited date is cleared', async () => {
    const { services } = await renderExpensesScreen({
      route: '/expenses',
      seed: { expenses: [draftExpense()] },
    });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit expense expense-1' }),
    );
    fireEvent.change(screen.getByLabelText('Amount'), {
      target: { value: '999' },
    });
    fireEvent.change(screen.getByLabelText('Date'), {
      target: { value: '' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save expense' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Date is required.');
    expect(alert).toHaveAttribute('id', 'expense-date-error');

    // The rejected edit must not have applied the amount it changed.
    await expect(services.expenses.list()).resolves.toEqual([
      expect.objectContaining({
        id: 'expense-1',
        category: 'inputs',
        amount: 120,
        date: '2026-01-01',
        supplier: 'Acme',
        status: 'draft',
      }),
    ]);
  });

  it('shows an inline error for a non-numeric amount and saves nothing', async () => {
    const { services } = await renderExpensesScreen({ route: '/expenses' });

    fireEvent.click(await screen.findByRole('button', { name: 'Add expense' }));
    fireEvent.change(screen.getByLabelText('Amount'), {
      target: { value: 'abc' },
    });
    fireEvent.change(screen.getByLabelText('Date'), {
      target: { value: '2026-01-18' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save expense' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Amount must be a number.');
    expect(alert).toHaveAttribute('id', 'expense-amount-error');

    await expect(services.expenses.list()).resolves.toEqual([]);
  });

  it('shows the uploaded receipt file name on an edited expense', async () => {
    const { services } = await renderExpensesScreen({
      route: '/expenses',
      seed: { expenses: [draftExpense()] },
    });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit expense expense-1' }),
    );

    const file = new File(['receipt'], 'receipt-february.pdf', {
      type: 'application/pdf',
    });
    fireEvent.change(screen.getByLabelText('Receipt attachment'), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save expense' }));

    expect(await screen.findByText('receipt-february.pdf')).toBeInTheDocument();

    await expect(services.expenses.list()).resolves.toEqual([
      expect.objectContaining({
        id: 'expense-1',
        amount: 120,
        status: 'draft',
        attachments: [
          expect.objectContaining({ name: 'receipt-february.pdf' }),
        ],
      }),
    ]);
  });

  it('surfaces the backend error when a posted expense delete is rejected', async () => {
    // The list still shows a draft, but the record was posted elsewhere, so
    // the backend rejects the delete and the error must reach the user.
    const { services } = await renderExpensesScreen({
      route: '/expenses',
      seed: { expenses: [draftExpense()] },
    });

    await services.expenses.post('expense-1');

    fireEvent.click(
      await screen.findByRole('button', { name: 'Delete expense expense-1' }),
    );

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Cannot delete a posted expense.');
  });
});
