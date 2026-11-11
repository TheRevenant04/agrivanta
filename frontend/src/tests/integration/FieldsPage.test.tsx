import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderSetupScreen } from '@/testUtils/renderSetup';

describe('FieldsPage', () => {
  it('shows an empty state with a create action when there are no fields', async () => {
    await renderSetupScreen({ route: '/fields' });

    expect(await screen.findByText('No fields yet.')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Add field' }),
    ).toBeInTheDocument();
  });

  it('adds a field with a name and area to the list after save', async () => {
    const { services } = await renderSetupScreen({ route: '/fields' });

    fireEvent.click(await screen.findByRole('button', { name: 'Add field' }));
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'North 40' },
    });
    fireEvent.change(screen.getByLabelText('Area'), {
      target: { value: '40' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save field' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Field saved.');
    expect(screen.getByText('North 40')).toBeInTheDocument();
    expect(screen.getByText('40')).toBeInTheDocument();

    await expect(services.fields.list()).resolves.toEqual([
      expect.objectContaining({ name: 'North 40', area: 40 }),
    ]);
  });

  it('shows an inline error next to a blank name and saves nothing', async () => {
    const { services } = await renderSetupScreen({ route: '/fields' });

    fireEvent.click(await screen.findByRole('button', { name: 'Add field' }));
    fireEvent.change(screen.getByLabelText('Area'), {
      target: { value: '10' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save field' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Field name is required.');
    expect(alert).toHaveAttribute('id', 'field-name-error');
    expect(screen.getByLabelText('Name')).toHaveAttribute(
      'aria-invalid',
      'true',
    );

    await expect(services.fields.list()).resolves.toEqual([]);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByText('No fields yet.')).toBeInTheDocument();
  });

  it.each([
    ['-5', 'Area cannot be negative.'],
    ['abc', 'Area must be a number.'],
  ])(
    'rejects a %s area with an inline error mirroring the backend rule',
    async (area, message) => {
      const { services } = await renderSetupScreen({ route: '/fields' });

      fireEvent.click(await screen.findByRole('button', { name: 'Add field' }));
      fireEvent.change(screen.getByLabelText('Name'), {
        target: { value: 'South 12' },
      });
      fireEvent.change(screen.getByLabelText('Area'), {
        target: { value: area },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Save field' }));

      const alert = await screen.findByRole('alert');
      expect(alert).toHaveTextContent(message);
      expect(alert).toHaveAttribute('id', 'field-area-error');
      expect(screen.getByLabelText('Area')).toHaveAttribute(
        'aria-invalid',
        'true',
      );

      await expect(services.fields.list()).resolves.toEqual([]);
    },
  );

  it('edits an existing field from the list', async () => {
    await renderSetupScreen({
      route: '/fields',
      seed: {
        fields: [
          { id: 'field-1', farmId: 'farm-1', name: 'North 40', area: 40 },
        ],
      },
    });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit North 40' }),
    );
    fireEvent.change(screen.getByLabelText('Area'), {
      target: { value: '42' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save field' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Field saved.');
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.queryByText('40')).not.toBeInTheDocument();
  });
});
