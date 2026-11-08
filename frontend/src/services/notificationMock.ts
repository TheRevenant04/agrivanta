import {
  ApiError,
  type Notification,
  type NotificationServices,
} from './types';

export interface NotificationMockOptions {
  seed?: Notification[];
  requireAuth: () => unknown;
}

export function createNotificationMock({
  seed = [],
  requireAuth,
}: NotificationMockOptions): NotificationServices {
  const notifications = seed.map((notification) => ({ ...notification }));

  return {
    notifications: {
      async list() {
        requireAuth();
        return [...notifications]
          .sort(
            (left, right) =>
              Date.parse(right.createdAt) - Date.parse(left.createdAt),
          )
          .map((notification) => ({ ...notification }));
      },
      async unreadCount() {
        requireAuth();
        return notifications.filter((notification) => !notification.read)
          .length;
      },
      async markRead(id) {
        requireAuth();
        const notification = notifications.find((item) => item.id === id);
        if (!notification) {
          throw new ApiError('Notification not found.', 404);
        }
        notification.read = true;
        notification.updatedAt = new Date().toISOString();
        return { ...notification };
      },
    },
  };
}
