import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { FarmSetupSeed } from '../services/farmSetupMock';
import type { HarvestSaleSeed } from '../services/harvestSaleMock';
import { renderHarvestSaleScreen } from '../testUtils/renderHarvestSale';

const FARM_SETUP: FarmSetupSeed = {
  units: [{ id: 'unit-kg', name: 'kg', baseMeasure: 'mass' }],
};

const SEED: HarvestSaleSeed = {
  cycles: [
    { id: 'cycle-1', label: 'North 40 — Wheat 2026' },
    { id: 'cycle-2', label: 'South 12 — Maize 2026' },
  ],
  customers: [
    { id: 'customer-1', name: 'Greenfield Grain Co.' },
    { id: 'customer-2', name: 'Harbour Mill' },
  ],
  harvests: [
    {
      id: 'harvest-1',
      cycleId: 'cycle-1',
      quantity: 100,
      unitId: 'unit-kg',
      date: '2026-03-01',
    },
  ],
  sales: [],
};

async function fillSale(input: {
  customerId?: string;
  harvestId?: string;
  quantity?: string;
  unitPrice?: string;
  date?: string;
}) {
  await screen.findByRole('option', { name: 'Greenfield Grain Co.' });
  await screen.findByRole('option', { name: /100 kg/ });

  if (input.customerId !== undefined) {
    fireEvent.change(screen.getByLabelText('Customer'), {
      target: { value: input.customerId },
    });
  }

  if (input.harvestId !== undefined) {
    fireEvent.change(screen.getByLabelText('Harvest'), {
      target: { value: input.harvestId },
    });
  }

  if (input.quantity !== undefined) {
    fireEvent.change(screen.getByLabelText('Quantity'), {
      target: { value: input.quantity },
    });
  }

  if (input.unitPrice !== undefined) {
    fireEvent.change(screen.getByLabelText('Unit price'), {
      target: { value: input.unitPrice },
    });
  }

  if (input.date !== undefined) {
    fireEvent.change(screen.getByLabelText('Date'), {
      target: { value: input.date },
    });
  }
}

function submitSale() {
  fireEvent.click(screen.getByRole('button', { name: 'Save sale' }));
}

describe('SalesPage', () => {
  it('offers customer, cycle/harvest link, quantity, unit price, and date', async () => {
    await renderHarvestSaleScreen({
      route: '/sales',
      farmSetup: FARM_SETUP,
      harvestSale: SEED,
    });

    expect(await screen.findByLabelText('Crop cycle')).toBeInTheDocument();
    expect(await screen.findByLabelText('Customer')).toBeInTheDocument();
    expect(await screen.findByLabelText('Harvest')).toBeInTheDocument();
    expect(screen.getByLabelText('Quantity')).toBeInTheDocument();
    expect(screen.getByLabelText('Unit price')).toBeInTheDocument();
    expect(screen.getByLabelText('Date')).toBeInTheDocument();
  });

  it('shows an empty state for a cycle with no sales', async () => {
    await renderHarvestSaleScreen({
      route: '/sales',
      farmSetup: FARM_SETUP,
      harvestSale: SEED,
    });

    expect(
      await screen.findByText('No sales for this cycle yet.'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Record sale' }),
    ).toBeInTheDocument();
  });

  it('saves a sale and lists it against the cycle', async () => {
    const { services } = await renderHarvestSaleScreen({
      route: '/sales',
      farmSetup: FARM_SETUP,
      harvestSale: SEED,
    });

    await fillSale({
      customerId: 'customer-1',
      harvestId: 'harvest-1',
      quantity: '10',
      unitPrice: '3.5',
      date: '2026-03-05',
    });
    submitSale();

    expect(await screen.findByRole('status')).toHaveTextContent('Sale saved.');
    expect(await screen.findByText('10 kg')).toBeInTheDocument();

    await expect(services.sales.list()).resolves.toEqual([
      expect.objectContaining({
        customerId: 'customer-1',
        harvestId: 'harvest-1',
        quantity: 10,
        unitPrice: 3.5,
        revenue: 35,
      }),
    ]);
  });

  it('shows the sold-exceeds-harvested error next to quantity and allows a corrected resubmission', async () => {
    const { services } = await renderHarvestSaleScreen({
      route: '/sales',
      farmSetup: FARM_SETUP,
      harvestSale: SEED,
    });

    await fillSale({
      customerId: 'customer-1',
      harvestId: 'harvest-1',
      quantity: '150',
      unitPrice: '3.5',
      date: '2026-03-05',
    });
    submitSale();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      'Sold quantity exceeds the harvested quantity available. Maximum sellable is 100.',
    );
    expect(alert).toHaveAttribute('id', 'sale-quantity-error');
    expect(screen.getByLabelText('Quantity')).toHaveAttribute(
      'aria-invalid',
      'true',
    );

    // Nothing was saved while the quantity exceeded the remaining harvest.
    await expect(services.sales.list()).resolves.toEqual([]);

    fireEvent.change(screen.getByLabelText('Quantity'), {
      target: { value: '60' },
    });
    submitSale();

    expect(await screen.findByRole('status')).toHaveTextContent('Sale saved.');
    expect(screen.queryByText(/Maximum sellable is/)).not.toBeInTheDocument();

    await expect(services.sales.list()).resolves.toEqual([
      expect.objectContaining({ quantity: 60, revenue: 210 }),
    ]);
  });

  it('shows inline errors for a blank quantity or date and saves nothing', async () => {
    const { services } = await renderHarvestSaleScreen({
      route: '/sales',
      farmSetup: FARM_SETUP,
      harvestSale: SEED,
    });

    await fillSale({
      customerId: 'customer-1',
      harvestId: 'harvest-1',
      unitPrice: '3.5',
      date: '2026-03-05',
    });
    submitSale();

    const quantityAlert = await screen.findByRole('alert');
    expect(quantityAlert).toHaveTextContent('Quantity is required.');
    expect(quantityAlert).toHaveAttribute('id', 'sale-quantity-error');

    await fillSale({ quantity: '10' });
    fireEvent.change(screen.getByLabelText('Date'), {
      target: { value: '' },
    });
    submitSale();

    const dateAlert = await screen.findByRole('alert');
    expect(dateAlert).toHaveTextContent('Date is required.');
    expect(dateAlert).toHaveAttribute('id', 'sale-date-error');

    await expect(services.sales.list()).resolves.toEqual([]);
  });
});
