import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderSetupScreen } from '@/testUtils/renderSetup';

describe('ActivityTemplatesPage', () => {
  it('shows the seeded standard templates', async () => {
    await renderSetupScreen({ route: '/activity-templates' });

    for (const name of [
      'Land preparation',
      'Planting',
      'Fertilizing',
      'Spraying',
      'Harvesting',
    ]) {
      expect(await screen.findByText(name)).toBeInTheDocument();
    }
  });

  it('adds a custom activity type to the template list', async () => {
    const { services } = await renderSetupScreen({
      route: '/activity-templates',
    });

    fireEvent.click(
      await screen.findByRole('button', { name: 'Add template' }),
    );
    fireEvent.change(screen.getByLabelText('Template name'), {
      target: { value: 'Irrigation' },
    });
    fireEvent.change(screen.getByLabelText('Category'), {
      target: { value: 'custom' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save template' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Template saved.',
    );

    const list = screen.getByRole('list');
    expect(within(list).getByText('Irrigation')).toBeInTheDocument();

    await expect(services.activityTypes.list()).resolves.toEqual([
      expect.objectContaining({ name: 'Land preparation', standard: true }),
      expect.objectContaining({ name: 'Planting', standard: true }),
      expect.objectContaining({ name: 'Fertilizing', standard: true }),
      expect.objectContaining({ name: 'Spraying', standard: true }),
      expect.objectContaining({ name: 'Harvesting', standard: true }),
      expect.objectContaining({
        name: 'Irrigation',
        category: 'custom',
        standard: false,
      }),
    ]);
  });

  it('shows an inline error for a blank template name and saves nothing', async () => {
    const { services } = await renderSetupScreen({
      route: '/activity-templates',
    });

    const before = await services.activityTypes.list();

    fireEvent.click(
      await screen.findByRole('button', { name: 'Add template' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Save template' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Template name is required.');
    expect(alert).toHaveAttribute('id', 'template-name-error');
    expect(screen.getByLabelText('Template name')).toHaveAttribute(
      'aria-invalid',
      'true',
    );

    await expect(services.activityTypes.list()).resolves.toHaveLength(
      before.length,
    );
  });

  it('shows an empty state when there are no templates at all', async () => {
    await renderSetupScreen({
      route: '/activity-templates',
      activities: { activityTypes: [] },
    });

    expect(
      await screen.findByText('No activity templates yet.'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Add template' }),
    ).toBeInTheDocument();
  });
});
