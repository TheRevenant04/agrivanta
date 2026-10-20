import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderSetupScreen } from '../testUtils/renderSetup';

describe('UnitsPage', () => {
  it('shows an empty state with a create action when there are no units', async () => {
    await renderSetupScreen({ route: '/units' });

    expect(await screen.findByText('No units yet.')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Add unit' }),
    ).toBeInTheDocument();
  });

  it('creates a unit with a base measure and adds it to the list', async () => {
    const { services } = await renderSetupScreen({ route: '/units' });

    fireEvent.click(await screen.findByRole('button', { name: 'Add unit' }));
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Kilogram' },
    });
    fireEvent.change(screen.getByLabelText('Base measure'), {
      target: { value: 'mass' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save unit' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Unit saved.');

    const list = screen.getByRole('list');
    expect(within(list).getByText('Kilogram')).toBeInTheDocument();
    expect(within(list).getByText('mass')).toBeInTheDocument();

    await expect(services.units.list()).resolves.toEqual([
      expect.objectContaining({ name: 'Kilogram', baseMeasure: 'mass' }),
    ]);
  });

  it('shows an inline error when the base measure category is omitted', async () => {
    const { services } = await renderSetupScreen({ route: '/units' });

    fireEvent.click(await screen.findByRole('button', { name: 'Add unit' }));
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Litre' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save unit' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      'A base measure category (mass, volume, or count) is required.',
    );
    expect(alert).toHaveAttribute('id', 'unit-base-measure-error');
    expect(screen.getByLabelText('Base measure')).toHaveAttribute(
      'aria-invalid',
      'true',
    );

    await expect(services.units.list()).resolves.toEqual([]);
  });

  it('rejects an unknown base measure category with the backend rule', async () => {
    const { services } = await renderSetupScreen({ route: '/units' });

    // The select only offers valid categories, so the guard is exercised at
    // the services boundary, exactly where the backend enforces it.
    await expect(
      services.units.create({ name: 'Ton', baseMeasure: 'weight' }),
    ).rejects.toMatchObject({
      status: 400,
      field: 'baseMeasure',
      message: 'Base measure must be one of: mass, volume, count.',
    });
    await expect(services.units.list()).resolves.toEqual([]);
  });
});
