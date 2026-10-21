import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { FarmSetupSeed } from '../services/farmSetupMock';
import { renderSetupScreen } from '../testUtils/renderSetup';
import { LowStockBadge } from './InventoryPage';

const UNIT_SEED: FarmSetupSeed = {
  units: [
    { id: 'unit-kg', name: 'Kilogram', baseMeasure: 'mass' },
    { id: 'unit-litre', name: 'Litre', baseMeasure: 'volume' },
  ],
};

function rowFor(element: HTMLElement): HTMLElement {
  const row = element.closest('li');

  expect(row).not.toBeNull();
  return row as HTMLElement;
}

describe('LowStockBadge', () => {
  it('renders the low-stock label', () => {
    render(<LowStockBadge />);

    expect(screen.getByText('Low stock')).toBeInTheDocument();
  });
});

describe('InventoryPage', () => {
  it('shows an empty state with a create action when there are no items', async () => {
    await renderSetupScreen({ route: '/inventory', seed: UNIT_SEED });

    expect(
      await screen.findByText('No inventory items yet.'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Add inventory item' }),
    ).toBeInTheDocument();
  });

  it('shows each item name, unit, reorder level, and current quantity', async () => {
    await renderSetupScreen({
      route: '/inventory',
      seed: UNIT_SEED,
      inventory: {
        items: [
          { id: 'item-1', name: 'Urea', unitId: 'unit-kg', reorderLevel: 20 },
        ],
        movements: [
          {
            id: 'movement-1',
            itemId: 'item-1',
            type: 'purchase',
            quantity: 100,
          },
        ],
      },
    });

    const row = rowFor(await screen.findByText('Urea'));

    expect(within(row).getByText('Kilogram')).toBeInTheDocument();
    expect(within(row).getByText('Reorder level 20')).toBeInTheDocument();
    expect(within(row).getByText('Current quantity 100')).toBeInTheDocument();
  });

  it('flags items at or below their reorder level with a low-stock badge', async () => {
    await renderSetupScreen({
      route: '/inventory',
      seed: UNIT_SEED,
      inventory: {
        items: [
          { id: 'item-1', name: 'Urea', unitId: 'unit-kg', reorderLevel: 20 },
          { id: 'item-2', name: 'Lime', unitId: 'unit-kg', reorderLevel: 10 },
          {
            id: 'item-3',
            name: 'Compost',
            unitId: 'unit-kg',
            reorderLevel: 10,
          },
        ],
        movements: [
          {
            id: 'movement-1',
            itemId: 'item-1',
            type: 'purchase',
            quantity: 20,
          },
          { id: 'movement-2', itemId: 'item-2', type: 'purchase', quantity: 5 },
          {
            id: 'movement-3',
            itemId: 'item-3',
            type: 'purchase',
            quantity: 50,
          },
        ],
      },
    });

    const atLevel = rowFor(await screen.findByText('Urea'));
    const belowLevel = rowFor(screen.getByText('Lime'));
    const aboveLevel = rowFor(screen.getByText('Compost'));

    expect(within(atLevel).getByText('Low stock')).toBeInTheDocument();
    expect(within(belowLevel).getByText('Low stock')).toBeInTheDocument();
    expect(within(aboveLevel).queryByText('Low stock')).not.toBeInTheDocument();
  });

  it('adds a created item to the list', async () => {
    const { services } = await renderSetupScreen({
      route: '/inventory',
      seed: UNIT_SEED,
    });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Add inventory item' }),
    );
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'DAP' },
    });
    fireEvent.change(screen.getByLabelText('Unit'), {
      target: { value: 'unit-kg' },
    });
    fireEvent.change(screen.getByLabelText('Reorder level'), {
      target: { value: '15' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'Save inventory item' }),
    );

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Inventory item saved.',
    );

    const row = rowFor(screen.getByText('DAP'));
    expect(within(row).getByText('Kilogram')).toBeInTheDocument();
    expect(within(row).getByText('Reorder level 15')).toBeInTheDocument();
    expect(within(row).getByText('Current quantity 0')).toBeInTheDocument();

    await expect(services.items.list()).resolves.toEqual([
      expect.objectContaining({
        name: 'DAP',
        unitId: 'unit-kg',
        reorderLevel: 15,
        currentQuantity: 0,
      }),
    ]);
  });

  it('shows an inline error for a blank name and saves nothing', async () => {
    const { services } = await renderSetupScreen({
      route: '/inventory',
      seed: UNIT_SEED,
    });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Add inventory item' }),
    );
    fireEvent.change(screen.getByLabelText('Unit'), {
      target: { value: 'unit-kg' },
    });
    fireEvent.change(screen.getByLabelText('Reorder level'), {
      target: { value: '10' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'Save inventory item' }),
    );

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Inventory item name is required.');
    expect(alert).toHaveAttribute('id', 'inventory-item-name-error');
    expect(screen.getByLabelText('Name')).toHaveAttribute(
      'aria-invalid',
      'true',
    );

    await expect(services.items.list()).resolves.toEqual([]);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByText('No inventory items yet.')).toBeInTheDocument();
  });

  it('increases the current quantity after a purchase movement is saved', async () => {
    const { services } = await renderSetupScreen({
      route: '/inventory',
      seed: UNIT_SEED,
      inventory: {
        items: [
          { id: 'item-1', name: 'Urea', unitId: 'unit-kg', reorderLevel: 0 },
        ],
      },
    });

    expect(await screen.findByText('Current quantity 0')).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: 'Record movement for Urea' }),
    );
    fireEvent.change(screen.getByLabelText('Quantity'), {
      target: { value: '100' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save movement' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Movement saved.',
    );
    expect(screen.getByText('Current quantity 100')).toBeInTheDocument();

    await expect(services.items.list()).resolves.toEqual([
      expect.objectContaining({ id: 'item-1', currentQuantity: 100 }),
    ]);
    await expect(services.movements.list('item-1')).resolves.toHaveLength(1);
  });

  it('decreases the current quantity after a usage movement is saved', async () => {
    const { services } = await renderSetupScreen({
      route: '/inventory',
      seed: UNIT_SEED,
      inventory: {
        items: [
          { id: 'item-1', name: 'Urea', unitId: 'unit-kg', reorderLevel: 0 },
        ],
        movements: [
          {
            id: 'movement-1',
            itemId: 'item-1',
            type: 'purchase',
            quantity: 100,
          },
        ],
      },
    });

    expect(await screen.findByText('Current quantity 100')).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: 'Record movement for Urea' }),
    );
    fireEvent.change(screen.getByLabelText('Type'), {
      target: { value: 'usage' },
    });
    fireEvent.change(screen.getByLabelText('Quantity'), {
      target: { value: '30' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save movement' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Movement saved.',
    );
    expect(screen.getByText('Current quantity 70')).toBeInTheDocument();

    await expect(services.items.list()).resolves.toEqual([
      expect.objectContaining({ id: 'item-1', currentQuantity: 70 }),
    ]);
  });

  it('renders a usage that exceeds the stock as an inline quantity error', async () => {
    const { services } = await renderSetupScreen({
      route: '/inventory',
      seed: UNIT_SEED,
      inventory: {
        items: [
          { id: 'item-1', name: 'Urea', unitId: 'unit-kg', reorderLevel: 0 },
        ],
        movements: [
          {
            id: 'movement-1',
            itemId: 'item-1',
            type: 'purchase',
            quantity: 100,
          },
        ],
      },
    });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Record movement for Urea' }),
    );
    fireEvent.change(screen.getByLabelText('Type'), {
      target: { value: 'usage' },
    });
    fireEvent.change(screen.getByLabelText('Quantity'), {
      target: { value: '150' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save movement' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      'Usage exceeds the available quantity (available: 100).',
    );
    expect(alert).toHaveAttribute('id', 'movement-quantity-error');
    expect(screen.getByLabelText('Quantity')).toHaveAttribute(
      'aria-invalid',
      'true',
    );

    expect(screen.getByText('Current quantity 100')).toBeInTheDocument();
    await expect(services.movements.list('item-1')).resolves.toHaveLength(1);
  });

  it('keeps the current quantity read-only and derived from movements', async () => {
    await renderSetupScreen({
      route: '/inventory',
      seed: UNIT_SEED,
      inventory: {
        items: [
          { id: 'item-1', name: 'Urea', unitId: 'unit-kg', reorderLevel: 20 },
        ],
        movements: [
          {
            id: 'movement-1',
            itemId: 'item-1',
            type: 'purchase',
            quantity: 100,
          },
          { id: 'movement-2', itemId: 'item-1', type: 'usage', quantity: 30 },
        ],
      },
    });

    const quantity = await screen.findByText('Current quantity 70');
    expect(quantity.tagName).toBe('SPAN');
    expect(screen.queryByLabelText('Current quantity')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Add inventory item' }));

    expect(screen.getByLabelText('Reorder level')).toBeInTheDocument();
    expect(screen.queryByLabelText('Current quantity')).not.toBeInTheDocument();
  });
});
