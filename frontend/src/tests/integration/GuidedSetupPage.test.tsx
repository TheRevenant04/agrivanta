import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '@/App';
import { MOCK_USERS, createMockServices } from '@/services/mockServices';
import { createSessionStore } from '@/services/sessionStore';
import { ApiError, type AgrivantaServices } from '@/services/types';

afterEach(cleanup);

async function renderGuidedSetup(
  configure?: (services: AgrivantaServices) => void | Promise<void>,
) {
  window.localStorage.clear();
  const store = createSessionStore(window.localStorage);
  const services = createMockServices({ store });
  await services.auth.login({
    email: MOCK_USERS[0].email,
    password: MOCK_USERS[0].password,
  });
  await configure?.(services);
  window.history.pushState({}, '', '/setup');
  render(<App services={services} store={store} />);
  return { services, store };
}

describe('GuidedSetupPage', () => {
  it('accepts the generated farm name without looping back to the farm step', async () => {
    const { services } = await renderGuidedSetup();
    expect(
      await screen.findByRole('heading', { name: 'Step 2 of 4: Fields' }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    expect(
      await screen.findByRole('heading', { name: 'Step 2 of 4: Fields' }),
    ).toBeInTheDocument();
    await expect(services.setupStatus.get()).resolves.toMatchObject({
      steps: { farm: true, fields: false },
      nextStep: 'fields',
    });
  });

  it('submits each setup step and completes after successful responses', async () => {
    const { services } = await renderGuidedSetup();

    expect(
      await screen.findByRole('heading', { name: 'Step 2 of 4: Fields' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Guided setup' })).toHaveAttribute(
      'href',
      '/setup',
    );
    const steps = within(screen.getByRole('list', { name: 'Setup steps' }));
    expect(steps.getByText(/^Farm/)).toBeInTheDocument();
    expect(steps.getByText('Fields')).toBeInTheDocument();
    expect(steps.getByText('Crops')).toBeInTheDocument();
    expect(steps.getByText('Initial crop cycle')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    fireEvent.change(screen.getByLabelText('Farm name'), {
      target: { value: 'Willow Creek' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(
      await screen.findByRole('heading', { name: 'Step 2 of 4: Fields' }),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Field name'), {
      target: { value: 'North Field' },
    });
    fireEvent.change(screen.getByLabelText('Area'), {
      target: { value: '12.5' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(
      await screen.findByRole('heading', { name: 'Step 3 of 4: Crops' }),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Crop name'), {
      target: { value: 'Wheat' },
    });
    fireEvent.change(screen.getByLabelText('Variety name'), {
      target: { value: 'Winter Wheat' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(
      await screen.findByRole('heading', {
        name: 'Step 4 of 4: Initial crop cycle',
      }),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Start date'), {
      target: { value: '2026-03-01' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Complete setup' }));
    expect(
      await screen.findByRole('heading', { name: 'Farm setup complete' }),
    ).toBeInTheDocument();

    await expect(services.farm.get()).resolves.toMatchObject({
      name: 'Willow Creek',
      reportingCurrency: 'USD',
    });
    await expect(services.fields.list()).resolves.toHaveLength(1);
    await expect(services.crops.list()).resolves.toMatchObject([
      { id: 'crop-1', name: 'Wheat' },
    ]);
    await expect(services.varieties.list()).resolves.toMatchObject([
      { id: 'variety-1', cropId: 'crop-1', name: 'Winter Wheat' },
    ]);
    await expect(services.cropCycles.list()).resolves.toMatchObject([
      {
        fieldId: 'field-1',
        cropId: 'crop-1',
        varietyId: 'variety-1',
        cycleType: 'annual',
        startDate: '2026-03-01',
      },
    ]);

    await expect(services.setupStatus.get()).resolves.toMatchObject({
      complete: true,
      nextStep: null,
    });
  });

  it('does not advance when the current step request fails', async () => {
    const { services } = await renderGuidedSetup((mockServices) => {
      vi.spyOn(mockServices.farm, 'update').mockRejectedValue(
        new ApiError('Farm update failed', 400),
      );
    });
    await screen.findByRole('heading', { name: 'Step 2 of 4: Fields' });
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));

    fireEvent.change(screen.getByLabelText('Farm name'), {
      target: { value: 'Willow Creek' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Farm update failed',
    );
    expect(
      screen.getByRole('heading', { name: 'Step 1 of 4: Farm' }),
    ).toBeInTheDocument();
    expect(services.farm.update).toHaveBeenCalled();
    await expect(services.fields.list()).resolves.toHaveLength(0);
  });

  it('resumes a partially saved crop step without duplicating the crop', async () => {
    const { services } = await renderGuidedSetup((mockServices) => {
      vi.spyOn(mockServices.varieties, 'create').mockRejectedValueOnce(
        new ApiError('Variety could not be saved.', 400),
      );
    });
    await screen.findByRole('heading', { name: 'Step 2 of 4: Fields' });
    fireEvent.change(screen.getByLabelText('Field name'), {
      target: { value: 'North Field' },
    });
    fireEvent.change(screen.getByLabelText('Area'), {
      target: { value: '12.5' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await screen.findByRole('heading', { name: 'Step 3 of 4: Crops' });
    fireEvent.change(screen.getByLabelText('Crop name'), {
      target: { value: 'Wheat' },
    });
    fireEvent.change(screen.getByLabelText('Variety name'), {
      target: { value: 'Winter Wheat' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Variety could not be saved.',
    );
    await expect(services.crops.list()).resolves.toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await screen.findByRole('heading', {
      name: 'Step 4 of 4: Initial crop cycle',
    });
    await expect(services.crops.list()).resolves.toHaveLength(1);
    await expect(services.varieties.list()).resolves.toHaveLength(1);
  });

  it('creates a variety for an existing crop before advancing setup', async () => {
    const { services } = await renderGuidedSetup(async (mockServices) => {
      await mockServices.crops.create({ name: 'Existing Wheat' });
    });
    expect((await services.setupStatus.get()).steps.crops).toBe(false);

    await screen.findByRole('heading', { name: 'Step 2 of 4: Fields' });
    fireEvent.change(screen.getByLabelText('Field name'), {
      target: { value: 'North Field' },
    });
    fireEvent.change(screen.getByLabelText('Area'), {
      target: { value: '12.5' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await screen.findByRole('heading', { name: 'Step 3 of 4: Crops' });
    fireEvent.change(screen.getByLabelText('Variety name'), {
      target: { value: 'Winter Wheat' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    await screen.findByRole('heading', {
      name: 'Step 4 of 4: Initial crop cycle',
    });
    await expect(services.crops.list()).resolves.toHaveLength(1);
    await expect(services.varieties.list()).resolves.toMatchObject([
      { cropId: 'crop-1', name: 'Winter Wheat' },
    ]);
    await expect(services.setupStatus.get()).resolves.toMatchObject({
      steps: { crops: true },
      nextStep: 'initialCycle',
    });
  });

  it('updates an existing field when returning to the fields step', async () => {
    const { services } = await renderGuidedSetup();
    await screen.findByRole('heading', { name: 'Step 2 of 4: Fields' });

    fireEvent.change(screen.getByLabelText('Field name'), {
      target: { value: 'North Field' },
    });
    fireEvent.change(screen.getByLabelText('Area'), {
      target: { value: '12.5' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await screen.findByRole('heading', { name: 'Step 3 of 4: Crops' });

    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(screen.getByLabelText('Field name')).toHaveValue('North Field');
    fireEvent.change(screen.getByLabelText('Field name'), {
      target: { value: 'South Field' },
    });
    fireEvent.change(screen.getByLabelText('Area'), {
      target: { value: '20' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    expect(
      await screen.findByRole('heading', { name: 'Step 3 of 4: Crops' }),
    ).toBeInTheDocument();
    await expect(services.fields.list()).resolves.toMatchObject([
      { id: 'field-1', name: 'South Field', area: 20 },
    ]);
  });

  it('preserves form data when going back and resumes the current step after reload', async () => {
    const { services, store } = await renderGuidedSetup();
    await screen.findByRole('heading', { name: 'Step 2 of 4: Fields' });
    fireEvent.change(screen.getByLabelText('Field name'), {
      target: { value: 'North Field' },
    });
    fireEvent.change(screen.getByLabelText('Area'), {
      target: { value: '12.5' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    fireEvent.change(screen.getByLabelText('Farm name'), {
      target: { value: 'Willow Creek' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByLabelText('Field name')).toHaveValue(
      'North Field',
    );

    cleanup();
    window.history.pushState({}, '', '/setup');
    render(<App services={services} store={store} />);

    expect(
      await screen.findByRole('heading', { name: 'Step 2 of 4: Fields' }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Field name')).toHaveValue('North Field');
    expect(screen.getByLabelText('Area')).toHaveValue(12.5);
  });
});
