import type { ServiceRequest } from './farmSetupHttp';
import type {
  Notification,
  NotificationPage,
  NotificationServices,
  UnreadCountResponse,
} from './types';

const PAGE_SIZE = 100;

export function createNotificationHttp(
  request: ServiceRequest,
): NotificationServices {
  return {
    notifications: {
      async list() {
        const notifications: Notification[] = [];
        let page = 1;

        while (true) {
          const result = await request<NotificationPage>(
            `/notifications?page=${page}&page_size=${PAGE_SIZE}`,
            { method: 'GET' },
            true,
          );
          notifications.push(...result.results);
          if (result.nextPage === null) return notifications;
          page = result.nextPage;
        }
      },
      async unreadCount() {
        const result = await request<UnreadCountResponse>(
          '/notifications/unread-count',
          { method: 'GET' },
          true,
        );
        return result.unreadCount;
      },
      markRead(id) {
        return request<Notification>(
          `/notifications/${encodeURIComponent(id)}/read`,
          { method: 'POST' },
          true,
        );
      },
    },
  };
}
