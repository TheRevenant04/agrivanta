import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderSetupScreen } from '../testUtils/renderSetup';

describe('FarmPage', () => {
  it("shows the farm's name and reporting currency", async () => {
    await renderSetupScreen({ route: '/farm' });

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Farm' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Willow Creek Farm')).toBeInTheDocument();
    expect(screen.getByText('USD')).toBeInTheDocument();
  });

  it('saves an edit with a visible confirmation', async () => {
    await renderSetupScreen({ route: '/farm' });
    await screen.findByText('Willow Creek Farm');

    fireEvent.click(screen.getByRole('button', { name: 'Edit farm' }));
    fireEvent.change(screen.getByLabelText('Farm name'), {
      target: { value: 'Riverbend Farm' },
    });
    fireEvent.change(screen.getByLabelText('Reporting currency'), {
      target: { value: 'eur' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save farm' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Farm saved.');
    expect(screen.getByText('Riverbend Farm')).toBeInTheDocument();
    expect(screen.getByText('EUR')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Save farm' }),
    ).not.toBeInTheDocument();
  });

  it('rejects a blank farm name with an inline error and saves nothing', async () => {
    const { services } = await renderSetupScreen({ route: '/farm' });
    await screen.findByText('Willow Creek Farm');

    fireEvent.click(screen.getByRole('button', { name: 'Edit farm' }));
    fireEvent.change(screen.getByLabelText('Farm name'), {
      target: { value: '   ' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save farm' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Farm name is required.');
    expect(alert).toHaveAttribute('id', 'farm-name-error');
    expect(screen.getByLabelText('Farm name')).toHaveAttribute(
      'aria-invalid',
      'true',
    );

    await expect(services.farm.get()).resolves.toMatchObject({
      name: 'Willow Creek Farm',
      reportingCurrency: 'USD',
    });
  });

  it('rejects an invalid reporting currency with an inline error', async () => {
    await renderSetupScreen({ route: '/farm' });
    await screen.findByText('Willow Creek Farm');

    fireEvent.click(screen.getByRole('button', { name: 'Edit farm' }));
    fireEvent.change(screen.getByLabelText('Reporting currency'), {
      target: { value: 'dollars' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save farm' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Reporting currency must be a three-letter code such as USD.',
    );
    expect(screen.getByLabelText('Reporting currency')).toHaveAttribute(
      'aria-invalid',
      'true',
    );
  });
});
