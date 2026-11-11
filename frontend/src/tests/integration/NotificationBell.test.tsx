import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NotificationBell } from '@/components/NotificationBell';
import { ServicesProvider } from '@/services/ServicesProvider';
import { createMockServices } from '@/services/mockServices';
import { createMemorySessionStore } from '@/services/sessionStore';
import type { Notification } from '@/services/types';

const notifications: Notification[] = [
  {
    id: 'old',
    type: 'warning',
    message: 'Older notification',
    read: false,
    createdAt: '2026-01-01T10:00:00Z',
    updatedAt: '2026-01-01T10:00:00Z',
  },
  {
    id: 'new',
    type: 'alert',
    message: 'Newest notification',
    read: false,
    createdAt: '2026-02-01T10:00:00Z',
    updatedAt: '2026-02-01T10:00:00Z',
  },
];

async function renderBell(seed: Notification[] = []) {
  const store = createMemorySessionStore();
  const services = createMockServices({ store, notifications: seed });
  await services.auth.login({
    email: 'owner@agrivanta.test',
    password: 'password123',
  });
  const markRead = vi.spyOn(services.notifications, 'markRead');
  render(
    <ServicesProvider services={services}>
      <NotificationBell />
    </ServicesProvider>,
  );
  return { markRead };
}

describe('NotificationBell', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('shows unread notifications newest first and updates the badge as items are read', async () => {
    const { markRead } = await renderBell(notifications);

    expect(
      await screen.findByLabelText('2 unread notifications'),
    ).toHaveTextContent('2');
    fireEvent.click(
      screen.getByRole('button', { name: 'Notifications, 2 unread' }),
    );

    const panel = await screen.findByRole('region', { name: 'Notifications' });
    const items = within(panel).getAllByRole('button');
    expect(items[0]).toHaveAccessibleName(
      'Unread notification: Newest notification',
    );
    expect(items[1]).toHaveAccessibleName(
      'Unread notification: Older notification',
    );

    fireEvent.click(items[0]);
    expect(screen.getByLabelText('1 unread notifications')).toHaveTextContent(
      '1',
    );
    expect(markRead).toHaveBeenCalledWith('new');
    expect(
      await within(panel).findByRole('button', {
        name: 'Read notification: Newest notification',
      }),
    ).toHaveClass('notification-panel__item--read');

    fireEvent.click(
      within(panel).getByRole('button', {
        name: 'Unread notification: Older notification',
      }),
    );
    await waitFor(() =>
      expect(screen.queryByLabelText(/unread notifications/)).toBeNull(),
    );
    expect(markRead).toHaveBeenCalledWith('old');
  });

  it('does not show a badge for read notifications and applies read styling', async () => {
    const readNotification = {
      ...notifications[0],
      read: true,
    };
    await renderBell([readNotification]);

    await waitFor(() =>
      expect(screen.queryByLabelText(/unread notifications/)).toBeNull(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Notifications' }));

    expect(await screen.findByText('Older notification')).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: 'Read notification: Older notification',
      }),
    ).toHaveClass('notification-panel__item--read');
  });

  it('shows an empty state when the user has no notifications', async () => {
    await renderBell();
    fireEvent.click(screen.getByRole('button', { name: 'Notifications' }));

    expect(
      await screen.findByText('No notifications yet.'),
    ).toBeInTheDocument();
  });
});
