import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderSetupScreen } from '../testUtils/renderSetup';

const CROP_AND_VARIETY_SEED = {
  crops: [
    { id: 'crop-a', name: 'Wheat' },
    { id: 'crop-b', name: 'Rice' },
  ],
  varieties: [
    { id: 'variety-1', cropId: 'crop-a', name: 'Durum' },
    { id: 'variety-2', cropId: 'crop-a', name: 'Spelt' },
    { id: 'variety-3', cropId: 'crop-b', name: 'Jasmine' },
  ],
};

function selectedOptionNames(select: HTMLSelectElement): string[] {
  return Array.from(select.options).map((option) => option.textContent ?? '');
}

describe('VarietiesPage', () => {
  it('shows an empty state with a create action when there are no crops', async () => {
    await renderSetupScreen({ route: '/varieties', seed: { crops: [] } });

    expect(await screen.findByText(/No crops yet/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Add crop' })).toBeInTheDocument();
  });

  it('creates a crop, then a variety for that crop, and lists both', async () => {
    await renderSetupScreen({ route: '/varieties', seed: { crops: [] } });

    // No crops yet: the create action leads to the crops screen.
    fireEvent.click(await screen.findByRole('link', { name: 'Add crop' }));
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Crops' }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Add crop' }));
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Maize' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save crop' }));
    await screen.findByRole('status');
    expect(screen.getByText('Maize')).toBeInTheDocument();

    // Back to varieties through the app navigation.
    fireEvent.click(screen.getByRole('link', { name: 'Varieties' }));
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Varieties' }),
    ).toBeInTheDocument();

    const cropSelect = (await screen.findByLabelText(
      'Crop',
    )) as HTMLSelectElement;
    const maizeOption = screen.getByRole('option', {
      name: 'Maize',
    }) as HTMLOptionElement;
    fireEvent.change(cropSelect, { target: { value: maizeOption.value } });

    fireEvent.click(await screen.findByRole('button', { name: 'Add variety' }));
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Golden Bantam' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save variety' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Variety saved.',
    );
    expect(
      within(screen.getByRole('list')).getByText('Golden Bantam'),
    ).toBeInTheDocument();
  });

  it('only offers varieties belonging to the selected crop in the selector', async () => {
    await renderSetupScreen({
      route: '/varieties',
      seed: CROP_AND_VARIETY_SEED,
    });

    const cropSelect = (await screen.findByLabelText(
      'Crop',
    )) as HTMLSelectElement;

    fireEvent.change(cropSelect, { target: { value: 'crop-a' } });
    let list = screen.getByRole('list');
    expect(within(list).getByText('Durum')).toBeInTheDocument();
    expect(within(list).getByText('Spelt')).toBeInTheDocument();
    expect(within(list).queryByText('Jasmine')).not.toBeInTheDocument();

    let varietySelect = screen.getByLabelText('Variety') as HTMLSelectElement;
    expect(selectedOptionNames(varietySelect)).toEqual([
      'Select a variety to edit…',
      'Durum',
      'Spelt',
    ]);

    fireEvent.change(cropSelect, { target: { value: 'crop-b' } });
    varietySelect = screen.getByLabelText('Variety') as HTMLSelectElement;
    expect(selectedOptionNames(varietySelect)).toEqual([
      'Select a variety to edit…',
      'Jasmine',
    ]);
    list = screen.getByRole('list');
    expect(within(list).getByText('Jasmine')).toBeInTheDocument();
    expect(within(list).queryByText('Durum')).not.toBeInTheDocument();
  });

  it('shows an empty state with a create action when the crop has no varieties', async () => {
    await renderSetupScreen({
      route: '/varieties',
      seed: { crops: [{ id: 'crop-a', name: 'Wheat' }] },
    });

    const cropSelect = (await screen.findByLabelText(
      'Crop',
    )) as HTMLSelectElement;
    fireEvent.change(cropSelect, { target: { value: 'crop-a' } });

    expect(
      await screen.findByText('No varieties for Wheat yet.'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Add variety' }),
    ).toBeInTheDocument();
  });

  it('shows an inline error for a blank variety name and saves nothing', async () => {
    const { services } = await renderSetupScreen({
      route: '/varieties',
      seed: { crops: [{ id: 'crop-a', name: 'Wheat' }] },
    });

    const cropSelect = (await screen.findByLabelText(
      'Crop',
    )) as HTMLSelectElement;
    fireEvent.change(cropSelect, { target: { value: 'crop-a' } });

    fireEvent.click(await screen.findByRole('button', { name: 'Add variety' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save variety' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Variety name is required.');

    await expect(services.varieties.list()).resolves.toEqual([]);
  });
});
