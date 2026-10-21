import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderExpensesScreen } from '../testUtils/renderExpenses';

describe('PaymentsPage', () => {
  it('shows an empty state with a create action when there are no payments', async () => {
    await renderExpensesScreen({ route: '/payments' });

    expect(await screen.findByText('No payments yet.')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Add payment' }),
    ).toBeInTheDocument();
  });

  it('saves a paid payment and lists it', async () => {
    const { services } = await renderExpensesScreen({ route: '/payments' });

    fireEvent.click(await screen.findByRole('button', { name: 'Add payment' }));
    fireEvent.change(screen.getByLabelText('Type'), {
      target: { value: 'paid' },
    });
    fireEvent.change(screen.getByLabelText('Amount'), {
      target: { value: '75' },
    });
    fireEvent.change(screen.getByLabelText('Date'), {
      target: { value: '2026-02-10' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save payment' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Payment saved.',
    );
    expect(screen.getByText('paid')).toBeInTheDocument();
    expect(screen.getByText('75')).toBeInTheDocument();

    await expect(services.payments.list()).resolves.toEqual([
      expect.objectContaining({
        type: 'paid',
        amount: 75,
        date: '2026-02-10',
      }),
    ]);
  });

  it('saves a received payment linked to an expense', async () => {
    const { services } = await renderExpensesScreen({ route: '/payments' });

    fireEvent.click(await screen.findByRole('button', { name: 'Add payment' }));
    fireEvent.change(screen.getByLabelText('Type'), {
      target: { value: 'received' },
    });
    fireEvent.change(screen.getByLabelText('Amount'), {
      target: { value: '500' },
    });
    fireEvent.change(screen.getByLabelText('Date'), {
      target: { value: '2026-02-11' },
    });
    fireEvent.change(screen.getByLabelText('Link to expense (optional)'), {
      target: { value: 'expense-3' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save payment' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Payment saved.',
    );
    expect(screen.getByText('received')).toBeInTheDocument();
    expect(screen.getByText('expense-3')).toBeInTheDocument();

    await expect(services.payments.list()).resolves.toEqual([
      expect.objectContaining({
        type: 'received',
        amount: 500,
        linkedExpenseId: 'expense-3',
      }),
    ]);
  });

  it('saves a received payment linked to a sale', async () => {
    const { services } = await renderExpensesScreen({ route: '/payments' });

    fireEvent.click(await screen.findByRole('button', { name: 'Add payment' }));
    fireEvent.change(screen.getByLabelText('Type'), {
      target: { value: 'received' },
    });
    fireEvent.change(screen.getByLabelText('Amount'), {
      target: { value: '300' },
    });
    fireEvent.change(screen.getByLabelText('Date'), {
      target: { value: '2026-02-13' },
    });
    fireEvent.change(screen.getByLabelText('Link to sale (optional)'), {
      target: { value: 'sale-7' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save payment' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Payment saved.',
    );
    expect(screen.getByText('sale-7')).toBeInTheDocument();

    await expect(services.payments.list()).resolves.toEqual([
      expect.objectContaining({
        type: 'received',
        amount: 300,
        date: '2026-02-13',
        linkedSaleId: 'sale-7',
      }),
    ]);
  });

  it('shows an inline error for a missing amount and saves nothing', async () => {
    const { services } = await renderExpensesScreen({ route: '/payments' });

    fireEvent.click(await screen.findByRole('button', { name: 'Add payment' }));
    fireEvent.change(screen.getByLabelText('Date'), {
      target: { value: '2026-02-12' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save payment' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Amount is required.');
    expect(alert).toHaveAttribute('id', 'payment-amount-error');
    expect(screen.getByLabelText('Amount')).toHaveAttribute(
      'aria-invalid',
      'true',
    );

    await expect(services.payments.list()).resolves.toEqual([]);
  });

  it('shows an inline error for a missing date and saves nothing', async () => {
    const { services } = await renderExpensesScreen({ route: '/payments' });

    fireEvent.click(await screen.findByRole('button', { name: 'Add payment' }));
    fireEvent.change(screen.getByLabelText('Amount'), {
      target: { value: '30' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save payment' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Date is required.');
    expect(alert).toHaveAttribute('id', 'payment-date-error');

    await expect(services.payments.list()).resolves.toEqual([]);
  });

  it('saves nothing and leaves existing payments untouched when a new one is invalid', async () => {
    const { services } = await renderExpensesScreen({
      route: '/payments',
      seed: {
        payments: [
          {
            id: 'payment-1',
            type: 'paid',
            amount: 25,
            date: '2026-02-01',
            reference: 'INV-1',
          },
        ],
      },
    });

    fireEvent.click(await screen.findByRole('button', { name: 'Add payment' }));
    fireEvent.change(screen.getByLabelText('Type'), {
      target: { value: 'received' },
    });
    fireEvent.change(screen.getByLabelText('Amount'), {
      target: { value: '40' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save payment' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Date is required.');
    expect(alert).toHaveAttribute('id', 'payment-date-error');

    // The rejected payment must not have been stored, and the payment that
    // was already there must be unchanged.
    await expect(services.payments.list()).resolves.toEqual([
      expect.objectContaining({
        id: 'payment-1',
        type: 'paid',
        amount: 25,
        date: '2026-02-01',
        reference: 'INV-1',
      }),
    ]);
  });
});
