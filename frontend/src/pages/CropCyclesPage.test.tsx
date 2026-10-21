import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { FarmSetupSeed } from '../services/farmSetupMock';
import type { CropCycle } from '../services/types';
import { renderCropCycleScreen } from '../testUtils/renderCropCycles';

const FARM_SETUP: FarmSetupSeed = {
  farm: { id: 'farm-1', name: 'Willow Creek Farm', reportingCurrency: 'USD' },
  fields: [
    { id: 'field-1', farmId: 'farm-1', name: 'North 40', area: 40 },
    { id: 'field-2', farmId: 'farm-1', name: 'South 12', area: 12 },
  ],
  crops: [
    { id: 'crop-1', name: 'Wheat' },
    { id: 'crop-2', name: 'Maize' },
  ],
  varieties: [
    { id: 'variety-1', cropId: 'crop-1', name: 'Durum' },
    { id: 'variety-2', cropId: 'crop-1', name: 'Spelt' },
    { id: 'variety-3', cropId: 'crop-2', name: 'Sweet' },
  ],
};

const WHEAT_CYCLE: CropCycle = {
  id: 'cycle-1',
  fieldId: 'field-1',
  cropId: 'crop-1',
  varietyId: 'variety-1',
  startDate: '2026-03-01',
  endDate: '2026-07-15',
  status: 'open',
  expectedYield: 12,
  expectedPrice: 250,
};

/** Overlaps WHEAT_CYCLE on the same field (May starts before July ends). */
const MAIZE_CYCLE: CropCycle = {
  id: 'cycle-2',
  fieldId: 'field-1',
  cropId: 'crop-2',
  varietyId: 'variety-3',
  startDate: '2026-05-01',
  status: 'open',
};

const SOUTH_CYCLE: CropCycle = {
  id: 'cycle-3',
  fieldId: 'field-2',
  cropId: 'crop-1',
  varietyId: 'variety-2',
  startDate: '2026-02-01',
  status: 'open',
};

const CLOSED_CYCLE: CropCycle = {
  ...WHEAT_CYCLE,
  id: 'cycle-8',
  status: 'closed',
};

describe('CropCyclesPage', () => {
  it('lists a field’s cycles with crop, variety, dates, and an open badge', async () => {
    await renderCropCycleScreen({
      farmSetup: FARM_SETUP,
      cropCycles: [WHEAT_CYCLE, MAIZE_CYCLE, SOUTH_CYCLE],
    });

    const row = (await screen.findByText('Wheat')).closest('li');
    expect(row).not.toBeNull();
    expect(within(row!).getByText('Durum')).toBeInTheDocument();
    expect(within(row!).getByText('Start: 2026-03-01')).toBeInTheDocument();
    expect(within(row!).getByText('End: 2026-07-15')).toBeInTheDocument();
    expect(within(row!).getByText('Expected yield: 12')).toBeInTheDocument();
    expect(within(row!).getByText('Expected price: 250')).toBeInTheDocument();
    expect(within(row!).getByText('open')).toBeInTheDocument();
  });

  it('shows both overlapping cycles on the same field', async () => {
    await renderCropCycleScreen({
      farmSetup: FARM_SETUP,
      cropCycles: [WHEAT_CYCLE, MAIZE_CYCLE, SOUTH_CYCLE],
    });

    const wheatRow = (await screen.findByText('Wheat')).closest('li')!;
    const maizeRow = screen.getByText('Maize').closest('li')!;

    expect(wheatRow).toBeInTheDocument();
    expect(maizeRow).toBeInTheDocument();
    // 2026-05-01 start overlaps the 2026-03-01..2026-07-15 cycle.
    expect(within(maizeRow).getByText('Start: 2026-05-01')).toBeInTheDocument();
    expect(within(maizeRow).getByText('End: —')).toBeInTheDocument();
    expect(within(maizeRow).getByText('open')).toBeInTheDocument();

    // The other field's cycle is not part of North 40's list.
    expect(screen.queryByText('Spelt')).not.toBeInTheDocument();
  });

  it('switches the list when another field is selected', async () => {
    await renderCropCycleScreen({
      farmSetup: FARM_SETUP,
      cropCycles: [WHEAT_CYCLE, MAIZE_CYCLE, SOUTH_CYCLE],
    });

    await screen.findByText('Wheat');
    fireEvent.change(screen.getByLabelText('Show cycles for field'), {
      target: { value: 'field-2' },
    });

    const row = (await screen.findByText('Spelt')).closest('li')!;
    expect(within(row).getByText('Wheat')).toBeInTheDocument();
    expect(within(row).getByText('Start: 2026-02-01')).toBeInTheDocument();
    expect(screen.queryByText('Maize')).not.toBeInTheDocument();
  });

  it('shows an empty state with a create action for a field with no cycles', async () => {
    await renderCropCycleScreen({ farmSetup: FARM_SETUP });

    expect(
      await screen.findByText('No crop cycles for this field yet.'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Add crop cycle' }),
    ).toBeInTheDocument();
  });

  it('creates a cycle from field, crop, variety, and start date with an open badge', async () => {
    const { services } = await renderCropCycleScreen({
      farmSetup: FARM_SETUP,
    });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Add crop cycle' }),
    );

    // The form starts on the selected field, first crop, and its first
    // variety, and switching crop swaps the variety options.
    expect(screen.getByLabelText('Field')).toHaveValue('field-1');
    expect(screen.getByLabelText('Variety')).toHaveValue('variety-1');
    fireEvent.change(screen.getByLabelText('Crop'), {
      target: { value: 'crop-2' },
    });
    expect(screen.getByLabelText('Variety')).toHaveValue('variety-3');
    fireEvent.change(screen.getByLabelText('Crop'), {
      target: { value: 'crop-1' },
    });

    fireEvent.change(screen.getByLabelText('Start date'), {
      target: { value: '2026-04-01' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save crop cycle' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Crop cycle saved.',
    );

    const row = screen.getByText('Wheat').closest('li')!;
    expect(within(row).getByText('Durum')).toBeInTheDocument();
    expect(within(row).getByText('Start: 2026-04-01')).toBeInTheDocument();
    expect(within(row).getByText('open')).toBeInTheDocument();

    await expect(services.cropCycles.list('field-1')).resolves.toEqual([
      expect.objectContaining({
        fieldId: 'field-1',
        cropId: 'crop-1',
        varietyId: 'variety-1',
        startDate: '2026-04-01',
        status: 'open',
      }),
    ]);
  });

  it('shows an inline error for a blank start date and saves nothing', async () => {
    const { services } = await renderCropCycleScreen({
      farmSetup: FARM_SETUP,
    });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Add crop cycle' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Save crop cycle' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Start date is required.');
    expect(alert).toHaveAttribute('id', 'cycle-start-date-error');
    expect(screen.getByLabelText('Start date')).toHaveAttribute(
      'aria-invalid',
      'true',
    );

    await expect(services.cropCycles.list('field-1')).resolves.toEqual([]);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(
      screen.getByText('No crop cycles for this field yet.'),
    ).toBeInTheDocument();
  });

  it('shows an inline error for a non-numeric expected price and saves nothing', async () => {
    const { services } = await renderCropCycleScreen({
      farmSetup: FARM_SETUP,
    });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Add crop cycle' }),
    );
    fireEvent.change(screen.getByLabelText('Start date'), {
      target: { value: '2026-04-01' },
    });
    fireEvent.change(screen.getByLabelText('Expected price'), {
      target: { value: 'abc' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save crop cycle' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Expected price must be a number.');
    expect(alert).toHaveAttribute('id', 'cycle-price-error');

    await expect(services.cropCycles.list('field-1')).resolves.toEqual([]);
  });

  it('saves an expected yield and price edit and shows the new values', async () => {
    const { services } = await renderCropCycleScreen({
      farmSetup: FARM_SETUP,
      cropCycles: [WHEAT_CYCLE],
    });

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Edit Wheat Durum (2026-03-01)',
      }),
    );
    fireEvent.change(screen.getByLabelText('Expected yield'), {
      target: { value: '15' },
    });
    fireEvent.change(screen.getByLabelText('Expected price'), {
      target: { value: '300' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save crop cycle' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Crop cycle updated.',
    );

    const row = screen.getByText('Wheat').closest('li')!;
    expect(within(row).getByText('Expected yield: 15')).toBeInTheDocument();
    expect(within(row).getByText('Expected price: 300')).toBeInTheDocument();
    expect(within(row).queryByText('Expected yield: 12')).toBeNull();

    await expect(services.cropCycles.list('field-1')).resolves.toEqual([
      expect.objectContaining({ expectedYield: 15, expectedPrice: 300 }),
    ]);
  });

  it('closes a cycle after confirming in a dialog that names it', async () => {
    const { services } = await renderCropCycleScreen({
      farmSetup: FARM_SETUP,
      cropCycles: [WHEAT_CYCLE],
    });

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Close Wheat Durum (2026-03-01)',
      }),
    );

    const dialog = await screen.findByRole('dialog', {
      name: 'Close Wheat Durum (2026-03-01)',
    });
    expect(dialog).toHaveTextContent('Wheat Durum (2026-03-01)');

    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Confirm close' }),
    );

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Crop cycle closed.',
    );
    expect(screen.queryByRole('dialog')).toBeNull();

    const row = screen.getByText('Wheat').closest('li')!;
    expect(within(row).getByText('closed')).toBeInTheDocument();
    expect(within(row).queryByRole('button', { name: /Edit/ })).toBeNull();
    expect(within(row).queryByRole('button', { name: /Close/ })).toBeNull();

    await expect(services.cropCycles.list('field-1')).resolves.toEqual([
      expect.objectContaining({ id: 'cycle-1', status: 'closed' }),
    ]);
  });

  it('leaves the cycle open when the confirmation is cancelled', async () => {
    const { services } = await renderCropCycleScreen({
      farmSetup: FARM_SETUP,
      cropCycles: [WHEAT_CYCLE],
    });

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Close Wheat Durum (2026-03-01)',
      }),
    );

    const dialog = await screen.findByRole('dialog');
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Keep cycle open' }),
    );

    expect(screen.queryByRole('dialog')).toBeNull();

    const row = screen.getByText('Wheat').closest('li')!;
    expect(within(row).getByText('open')).toBeInTheDocument();
    expect(
      within(row).getByRole('button', { name: /Edit/ }),
    ).toBeInTheDocument();

    await expect(services.cropCycles.list('field-1')).resolves.toEqual([
      expect.objectContaining({ id: 'cycle-1', status: 'open' }),
    ]);
  });

  it('hides edit and close controls for a closed cycle', async () => {
    await renderCropCycleScreen({
      farmSetup: FARM_SETUP,
      cropCycles: [CLOSED_CYCLE, MAIZE_CYCLE],
    });

    const closedRow = (await screen.findByText('Wheat')).closest('li')!;
    expect(within(closedRow).getByText('closed')).toBeInTheDocument();
    expect(
      within(closedRow).queryByRole('button', { name: /Edit/ }),
    ).toBeNull();
    expect(
      within(closedRow).queryByRole('button', { name: /Close/ }),
    ).toBeNull();

    // The open cycle on the same field keeps its controls.
    const openRow = screen.getByText('Maize').closest('li')!;
    expect(
      within(openRow).getByRole('button', { name: /Edit/ }),
    ).toBeInTheDocument();
    expect(
      within(openRow).getByRole('button', { name: /Close/ }),
    ).toBeInTheDocument();
  });
});
