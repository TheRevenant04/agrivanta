import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { FarmSetupSeed } from '../services/farmSetupMock';
import type { HarvestSaleSeed } from '../services/harvestSaleMock';
import { renderHarvestSaleScreen } from '../testUtils/renderHarvestSale';

const FARM_SETUP: FarmSetupSeed = {
  units: [
    { id: 'unit-kg', name: 'kg', baseMeasure: 'mass' },
    { id: 'unit-g', name: 'g', baseMeasure: 'mass' },
  ],
};

const CYCLES = [
  { id: 'cycle-1', label: 'North 40 — Wheat 2026' },
  { id: 'cycle-2', label: 'South 12 — Maize 2026' },
];

const SEED: HarvestSaleSeed = {
  cycles: CYCLES,
  customers: [{ id: 'customer-1', name: 'Greenfield Grain Co.' }],
  harvests: [],
  sales: [],
};

async function addHarvest(input: {
  quantity?: string;
  unitId?: string;
  date?: string;
}) {
  if (input.quantity !== undefined) {
    fireEvent.change(screen.getByLabelText('Quantity'), {
      target: { value: input.quantity },
    });
  }

  if (input.unitId !== undefined) {
    fireEvent.change(screen.getByLabelText('Unit'), {
      target: { value: input.unitId },
    });
  }

  if (input.date !== undefined) {
    fireEvent.change(screen.getByLabelText('Date'), {
      target: { value: input.date },
    });
  }

  fireEvent.click(screen.getByRole('button', { name: 'Save harvest' }));
}

describe('HarvestsPage', () => {
  it('shows an empty state and a zero total for a cycle with no harvests', async () => {
    await renderHarvestSaleScreen({
      route: '/harvests',
      farmSetup: FARM_SETUP,
      harvestSale: SEED,
    });

    expect(
      await screen.findByText('No harvests for this cycle yet.'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Record harvest' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Harvested total: 0')).toBeInTheDocument();
  });

  it('saves a harvest and increases the harvested total shown', async () => {
    const { services } = await renderHarvestSaleScreen({
      route: '/harvests',
      farmSetup: FARM_SETUP,
      harvestSale: SEED,
    });

    await screen.findByText('No harvests for this cycle yet.');

    await addHarvest({
      quantity: '40',
      unitId: 'unit-kg',
      date: '2026-03-01',
    });

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Harvest saved.',
    );
    expect(
      await screen.findByText('Harvested total: 40 kg'),
    ).toBeInTheDocument();
    expect(screen.getByText('40 kg')).toBeInTheDocument();

    await addHarvest({
      quantity: '10',
      unitId: 'unit-kg',
      date: '2026-03-02',
    });

    expect(
      await screen.findByText('Harvested total: 50 kg'),
    ).toBeInTheDocument();

    await expect(services.harvests.list('cycle-1')).resolves.toEqual([
      expect.objectContaining({ quantity: 40, unitId: 'unit-kg' }),
      expect.objectContaining({ quantity: 10, unitId: 'unit-kg' }),
    ]);
  });

  it('shows an inline error for a blank quantity and saves nothing', async () => {
    const { services } = await renderHarvestSaleScreen({
      route: '/harvests',
      farmSetup: FARM_SETUP,
      harvestSale: SEED,
    });

    await screen.findByText('No harvests for this cycle yet.');
    await addHarvest({ unitId: 'unit-kg', date: '2026-03-01' });

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Quantity is required.');
    expect(alert).toHaveAttribute('id', 'harvest-quantity-error');
    expect(screen.getByLabelText('Quantity')).toHaveAttribute(
      'aria-invalid',
      'true',
    );

    await expect(services.harvests.list()).resolves.toEqual([]);
  });

  it('shows an inline error for a blank date and saves nothing', async () => {
    const { services } = await renderHarvestSaleScreen({
      route: '/harvests',
      farmSetup: FARM_SETUP,
      harvestSale: SEED,
    });

    await screen.findByText('No harvests for this cycle yet.');
    await addHarvest({ quantity: '12', unitId: 'unit-kg' });

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Date is required.');
    expect(alert).toHaveAttribute('id', 'harvest-date-error');
    expect(screen.getByLabelText('Date')).toHaveAttribute(
      'aria-invalid',
      'true',
    );

    await expect(services.harvests.list()).resolves.toEqual([]);
  });

  it('lists only the selected cycle\u2019s harvests', async () => {
    await renderHarvestSaleScreen({
      route: '/harvests',
      farmSetup: FARM_SETUP,
      harvestSale: {
        ...SEED,
        harvests: [
          {
            id: 'harvest-1',
            cycleId: 'cycle-1',
            quantity: 75,
            unitId: 'unit-kg',
            date: '2026-03-01',
          },
        ],
      },
    });

    expect(
      await screen.findByText('Harvested total: 75 kg'),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Crop cycle'), {
      target: { value: 'cycle-2' },
    });

    expect(
      await screen.findByText('No harvests for this cycle yet.'),
    ).toBeInTheDocument();
    expect(await screen.findByText('Harvested total: 0')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Crop cycle'), {
      target: { value: 'cycle-1' },
    });

    expect(
      await screen.findByText('Harvested total: 75 kg'),
    ).toBeInTheDocument();
  });
});
