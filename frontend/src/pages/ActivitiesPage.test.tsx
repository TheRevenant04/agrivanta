import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ActivityPlanningSeed } from '../services/activityPlanningMock';
import { renderSetupScreen } from '../testUtils/renderSetup';

const PLANNING_SEED: ActivityPlanningSeed = {
  activityTypes: [
    {
      id: 'type-planting',
      name: 'Planting',
      category: 'planting',
      standard: true,
    },
    {
      id: 'type-harvest',
      name: 'Harvesting',
      category: 'harvesting',
      standard: true,
    },
  ],
  cycles: [
    { id: 'cycle-1', label: 'North 40 — Wheat 2026' },
    { id: 'cycle-2', label: 'South 12 — Maize 2026' },
  ],
  activities: [
    {
      id: 'activity-1',
      cycleId: 'cycle-1',
      typeId: 'type-planting',
      plannedDate: '2026-03-01',
      status: 'planned',
      resourceNeeds: {
        inputs: [{ id: 'need-1', itemName: 'Seed', quantity: 10 }],
        labourHours: 4,
        equipment: 'Tractor',
      },
    },
    {
      id: 'activity-2',
      cycleId: 'cycle-2',
      typeId: 'type-harvest',
      plannedDate: '2026-08-01',
      status: 'overdue',
      resourceNeeds: { inputs: [], labourHours: 0, equipment: '' },
    },
  ],
};

async function activityRow(typeName: string): Promise<HTMLElement> {
  const heading = await screen.findByText(typeName);
  const row = heading.closest('li');

  if (!row) {
    throw new Error(`No list row found for ${typeName}`);
  }

  return row as HTMLElement;
}

describe('ActivitiesPage', () => {
  it('shows an empty state with a create action when there are no activities', async () => {
    await renderSetupScreen({ route: '/activities' });

    expect(await screen.findByText('No activities yet.')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Create activity' }),
    ).toBeInTheDocument();
  });

  it('filters the activity list to the picked crop cycle only', async () => {
    await renderSetupScreen({
      route: '/activities',
      activities: PLANNING_SEED,
    });

    expect(await screen.findByText('Planting')).toBeInTheDocument();
    expect(screen.getByText('Harvesting')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Crop cycle'), {
      target: { value: 'cycle-1' },
    });

    await waitFor(() => {
      expect(screen.queryByText('Harvesting')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Planting')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Crop cycle'), {
      target: { value: 'cycle-2' },
    });

    await waitFor(() => {
      expect(screen.getByText('Harvesting')).toBeInTheDocument();
    });
    expect(screen.queryByText('Planting')).not.toBeInTheDocument();
  });

  it('shows a cycle with no activities as an empty state with a create action', async () => {
    await renderSetupScreen({
      route: '/activities',
      activities: {
        cycles: [
          { id: 'cycle-1', label: 'North 40 — Wheat 2026' },
          { id: 'cycle-empty', label: 'West 8 — Barley 2026' },
        ],
      },
    });

    fireEvent.change(await screen.findByLabelText('Crop cycle'), {
      target: { value: 'cycle-empty' },
    });

    expect(
      await screen.findByText('No activities for this cycle.'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Create activity' }),
    ).toBeInTheDocument();
  });

  it('adds an activity with a type and planned date showing a planned badge', async () => {
    const { services } = await renderSetupScreen({
      route: '/activities',
      activities: {
        activityTypes: PLANNING_SEED.activityTypes,
        cycles: [{ id: 'cycle-1', label: 'North 40 — Wheat 2026' }],
      },
    });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Create activity' }),
    );
    fireEvent.change(screen.getByLabelText('Type'), {
      target: { value: 'type-planting' },
    });
    fireEvent.change(screen.getByLabelText('Planned date'), {
      target: { value: '2026-05-01' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save activity' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Activity saved.',
    );

    const row = await activityRow('Planting');
    expect(within(row).getByText('planned')).toBeInTheDocument();
    expect(within(row).getByText('2026-05-01')).toBeInTheDocument();

    await expect(services.activities.list('cycle-1')).resolves.toEqual([
      expect.objectContaining({
        typeId: 'type-planting',
        plannedDate: '2026-05-01',
        status: 'planned',
      }),
    ]);
  });

  it('shows an inline error next to a blank planned date and saves nothing', async () => {
    const { services } = await renderSetupScreen({ route: '/activities' });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Create activity' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Save activity' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Planned date is required.');
    expect(alert).toHaveAttribute('id', 'activity-planned-date-error');
    expect(screen.getByLabelText('Planned date')).toHaveAttribute(
      'aria-invalid',
      'true',
    );

    await expect(services.activities.list()).resolves.toEqual([]);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByText('No activities yet.')).toBeInTheDocument();
  });

  it('saves edited resource needs and re-displays the new row values', async () => {
    const { services } = await renderSetupScreen({
      route: '/activities',
      activities: PLANNING_SEED,
    });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit needs Planting' }),
    );

    fireEvent.change(screen.getByLabelText('Item'), {
      target: { value: 'Fertilizer' },
    });
    fireEvent.change(screen.getByLabelText('Quantity'), {
      target: { value: '25' },
    });
    fireEvent.change(screen.getByLabelText('Labour hours'), {
      target: { value: '12' },
    });
    fireEvent.change(screen.getByLabelText('Equipment'), {
      target: { value: 'Spreaders' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'Save resource needs' }),
    );

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Resource needs saved.',
    );

    const row = await activityRow('Planting');
    expect(within(row).getByText('25 × Fertilizer')).toBeInTheDocument();
    expect(within(row).getByText('Labour: 12 hours')).toBeInTheDocument();
    expect(within(row).getByText('Equipment: Spreaders')).toBeInTheDocument();
    expect(within(row).queryByText(/10 × Seed/)).not.toBeInTheDocument();

    await expect(services.activities.list('cycle-1')).resolves.toEqual([
      expect.objectContaining({
        resourceNeeds: {
          inputs: [
            { id: expect.any(String), itemName: 'Fertilizer', quantity: 25 },
          ],
          labourHours: 12,
          equipment: 'Spreaders',
        },
      }),
    ]);
  });

  it('rejects malformed resource needs with an inline error and saves nothing', async () => {
    const { services } = await renderSetupScreen({
      route: '/activities',
      activities: PLANNING_SEED,
    });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit needs Planting' }),
    );
    fireEvent.change(screen.getByLabelText('Labour hours'), {
      target: { value: '   ' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'Save resource needs' }),
    );

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Labour hours are required.');
    expect(alert).toHaveAttribute('id', 'needs-labour-hours-error');

    await expect(services.activities.list('cycle-1')).resolves.toEqual([
      expect.objectContaining({
        resourceNeeds: {
          inputs: [{ id: 'need-1', itemName: 'Seed', quantity: 10 }],
          labourHours: 4,
          equipment: 'Tractor',
        },
      }),
    ]);
  });

  it('moves an activity planned → in progress → completed via inline buttons', async () => {
    const { services } = await renderSetupScreen({
      route: '/activities',
      activities: PLANNING_SEED,
    });

    const row = await activityRow('Planting');
    expect(within(row).getByText('planned')).toBeInTheDocument();

    fireEvent.click(
      within(row).getByRole('button', { name: 'Start Planting' }),
    );

    expect(await within(row).findByText('in progress')).toBeInTheDocument();
    expect(within(row).queryByText('planned')).not.toBeInTheDocument();

    fireEvent.click(
      within(row).getByRole('button', { name: 'Complete Planting' }),
    );

    expect(await within(row).findByText('completed')).toBeInTheDocument();
    expect(within(row).queryByText('in progress')).not.toBeInTheDocument();
    expect(
      within(row).queryByRole('button', { name: 'Start Planting' }),
    ).not.toBeInTheDocument();
    expect(
      within(row).queryByRole('button', { name: 'Complete Planting' }),
    ).not.toBeInTheDocument();

    await expect(services.activities.list('cycle-1')).resolves.toEqual([
      expect.objectContaining({ status: 'completed' }),
    ]);
  });

  it('renders an overdue badge for an activity the API reports as overdue', async () => {
    await renderSetupScreen({
      route: '/activities',
      activities: PLANNING_SEED,
    });

    const row = await activityRow('Harvesting');

    expect(within(row).getByText('overdue')).toBeInTheDocument();
    expect(
      within(row).getByRole('button', { name: 'Start Harvesting' }),
    ).toBeInTheDocument();
  });
});
