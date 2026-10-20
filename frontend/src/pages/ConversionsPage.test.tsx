import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderSetupScreen } from '../testUtils/renderSetup';
import type { FarmSetupSeed } from '../services/farmSetupMock';

const UNITS: FarmSetupSeed = {
  units: [
    { id: 'unit-kg', name: 'Kilogram', baseMeasure: 'mass' },
    { id: 'unit-lb', name: 'Pound', baseMeasure: 'mass' },
    { id: 'unit-oz', name: 'Ounce', baseMeasure: 'mass' },
    { id: 'unit-litre', name: 'Litre', baseMeasure: 'volume' },
  ],
};

describe('ConversionsPage', () => {
  it('shows an empty state with a create action when there are no rules', async () => {
    await renderSetupScreen({ route: '/conversions', seed: UNITS });

    expect(
      await screen.findByText('No conversion rules yet.'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Add conversion rule' }),
    ).toBeInTheDocument();
  });

  it('shows an empty state leading to unit creation when no units exist', async () => {
    await renderSetupScreen({ route: '/conversions', seed: { units: [] } });

    expect(await screen.findByText(/No units yet/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Add unit' })).toBeInTheDocument();
  });

  it('adds a conversion rule from unit to unit with a factor', async () => {
    const { services } = await renderSetupScreen({
      route: '/conversions',
      seed: UNITS,
    });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Add conversion rule' }),
    );
    fireEvent.change(screen.getByLabelText('From unit'), {
      target: { value: 'unit-kg' },
    });
    fireEvent.change(screen.getByLabelText('To unit'), {
      target: { value: 'unit-lb' },
    });
    fireEvent.change(screen.getByLabelText('Factor'), {
      target: { value: '2.2' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'Save conversion rule' }),
    );

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Conversion rule saved.',
    );

    const rules = within(screen.getByRole('list')).getAllByRole('listitem');
    expect(rules).toHaveLength(1);
    expect(rules[0]).toHaveTextContent('Kilogram');
    expect(rules[0]).toHaveTextContent('Pound');
    expect(rules[0]).toHaveTextContent('2.2');

    await expect(services.conversions.list()).resolves.toEqual([
      expect.objectContaining({
        fromUnitId: 'unit-kg',
        toUnitId: 'unit-lb',
        factor: 2.2,
      }),
    ]);
  });

  it('shows an inline error for a non-positive conversion factor', async () => {
    await renderSetupScreen({ route: '/conversions', seed: UNITS });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Add conversion rule' }),
    );
    fireEvent.change(screen.getByLabelText('From unit'), {
      target: { value: 'unit-lb' },
    });
    fireEvent.change(screen.getByLabelText('To unit'), {
      target: { value: 'unit-oz' },
    });
    fireEvent.change(screen.getByLabelText('Factor'), {
      target: { value: '-2' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'Save conversion rule' }),
    );

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      'Conversion factor must be a positive number.',
    );
    expect(screen.getByLabelText('Factor')).toHaveAttribute(
      'aria-invalid',
      'true',
    );
  });

  it("displays the backend's no rule exists error inline for an unmatched conversion", async () => {
    const { services } = await renderSetupScreen({
      route: '/conversions',
      seed: UNITS,
    });

    fireEvent.change(await screen.findByLabelText('Convert from'), {
      target: { value: 'unit-kg' },
    });
    fireEvent.change(screen.getByLabelText('Convert to'), {
      target: { value: 'unit-oz' },
    });
    fireEvent.change(screen.getByLabelText('Quantity'), {
      target: { value: '100' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Convert' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      'No rule exists for converting from "Kilogram" to "Ounce".',
    );
    expect(alert).toHaveTextContent(/no rule exists/i);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    await expect(services.conversions.list()).resolves.toEqual([]);
  });

  it('names the base measure mismatch when converting across categories', async () => {
    await renderSetupScreen({ route: '/conversions', seed: UNITS });

    fireEvent.change(await screen.findByLabelText('Convert from'), {
      target: { value: 'unit-kg' },
    });
    fireEvent.change(screen.getByLabelText('Convert to'), {
      target: { value: 'unit-litre' },
    });
    fireEvent.change(screen.getByLabelText('Quantity'), {
      target: { value: '1' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Convert' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Cannot convert "Kilogram" (mass) to "Litre" (volume): base measures do not match.',
    );
  });

  it('converts a quantity when a rule exists', async () => {
    await renderSetupScreen({
      route: '/conversions',
      seed: {
        ...UNITS,
        conversions: [
          {
            id: 'conv-1',
            fromUnitId: 'unit-kg',
            toUnitId: 'unit-lb',
            factor: 2.2,
          },
        ],
      },
    });

    fireEvent.change(await screen.findByLabelText('Convert from'), {
      target: { value: 'unit-kg' },
    });
    fireEvent.change(screen.getByLabelText('Convert to'), {
      target: { value: 'unit-lb' },
    });
    fireEvent.change(screen.getByLabelText('Quantity'), {
      target: { value: '10' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Convert' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      '10 Kilogram = 22 Pound',
    );
  });
});
