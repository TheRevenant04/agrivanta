import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderSetupScreen } from '@/testUtils/renderSetup';

describe('CropsPage', () => {
  it('shows an empty state with a create action when there are no crops', async () => {
    await renderSetupScreen({ route: '/crops' });

    expect(await screen.findByText('No crops yet.')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Add crop' }),
    ).toBeInTheDocument();
  });

  it('creates a crop and adds it to the list', async () => {
    const { services } = await renderSetupScreen({ route: '/crops' });

    fireEvent.click(await screen.findByRole('button', { name: 'Add crop' }));
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Wheat' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save crop' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Crop saved.');
    expect(screen.getByText('Wheat')).toBeInTheDocument();

    await expect(services.crops.list()).resolves.toEqual([
      expect.objectContaining({ name: 'Wheat' }),
    ]);
  });

  it('shows an inline error for a blank crop name and saves nothing', async () => {
    const { services } = await renderSetupScreen({ route: '/crops' });

    fireEvent.click(await screen.findByRole('button', { name: 'Add crop' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save crop' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Crop name is required.');
    expect(screen.getByLabelText('Name')).toHaveAttribute(
      'aria-invalid',
      'true',
    );

    await expect(services.crops.list()).resolves.toEqual([]);
  });

  it('rejects a duplicate crop name with the backend error inline', async () => {
    await renderSetupScreen({
      route: '/crops',
      seed: { crops: [{ id: 'crop-1', name: 'Wheat' }] },
    });

    fireEvent.click(await screen.findByRole('button', { name: 'Add crop' }));
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'wheat' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save crop' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'A crop named "wheat" already exists.',
    );
  });
});
