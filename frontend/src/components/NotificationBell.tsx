import { useCallback, useEffect, useRef, useState } from 'react';
import { Bell } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useServices } from '../services/servicesContext';
import type { Notification } from '../services/types';
import { Button } from './ui/button';

function newestFirst(notifications: Notification[]): Notification[] {
  return [...notifications].sort(
    (left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt),
  );
}

export function NotificationBell() {
  const services = useServices();
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [hasError, setHasError] = useState(false);
  const requestId = useRef(0);
  const markingRead = useRef(new Set<string>());

  const refreshNotifications = useCallback(async () => {
    const currentRequestId = ++requestId.current;
    setIsLoading(true);
    setHasError(false);

    try {
      const [items, count] = await Promise.all([
        services.notifications.list(),
        services.notifications.unreadCount(),
      ]);
      if (requestId.current !== currentRequestId) return;
      setNotifications(newestFirst(items));
      setUnreadCount(count);
    } catch {
      if (requestId.current === currentRequestId) setHasError(true);
    } finally {
      if (requestId.current === currentRequestId) setIsLoading(false);
    }
  }, [services]);

  useEffect(() => {
    queueMicrotask(() => void refreshNotifications());
    return () => {
      requestId.current += 1;
    };
  }, [refreshNotifications]);

  const togglePanel = () => {
    const willOpen = !isOpen;
    setIsOpen(willOpen);
    if (willOpen) void refreshNotifications();
  };

  const markRead = async (notification: Notification) => {
    if (notification.read || markingRead.current.has(notification.id)) return;

    markingRead.current.add(notification.id);
    setNotifications((current) =>
      current.map((item) =>
        item.id === notification.id ? { ...item, read: true } : item,
      ),
    );
    setUnreadCount((current) => Math.max(0, current - 1));

    try {
      const updated = await services.notifications.markRead(notification.id);
      setNotifications((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
    } catch {
      await refreshNotifications();
    } finally {
      markingRead.current.delete(notification.id);
    }
  };

  return (
    <div className="relative">
      <Button
        aria-label={`Notifications${unreadCount ? `, ${unreadCount} unread` : ''}`}
        aria-expanded={isOpen}
        aria-controls="notification-panel"
        variant="ghost"
        size="sm"
        className="relative"
        onClick={togglePanel}
        type="button"
      >
        <Bell aria-hidden="true" />
        <span>Notifications</span>
        {unreadCount > 0 && (
          <span
            aria-label={`${unreadCount} unread notifications`}
            className="inline-flex min-h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1 text-xs font-semibold leading-none text-destructive-foreground"
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </Button>
      {isOpen && (
        <section
          aria-label="Notifications"
          className="absolute right-0 top-full z-20 mt-2 max-h-96 min-w-80 overflow-y-auto rounded-xl border bg-popover p-2 text-popover-foreground shadow-lg"
          id="notification-panel"
        >
          <h2 className="px-3 pb-2 pt-2">Notifications</h2>
          {isLoading ? (
            <p role="status" className="px-3 pb-3">
              Loading notifications…
            </p>
          ) : hasError ? (
            <div className="space-y-3 px-3 pb-3">
              <p role="alert">Unable to load notifications.</p>
              <Button
                onClick={() => void refreshNotifications()}
                size="sm"
                type="button"
                variant="outline"
              >
                Try again
              </Button>
            </div>
          ) : notifications.length === 0 ? (
            <p className="px-3 pb-3">No notifications yet.</p>
          ) : (
            <ul className="space-y-1">
              {notifications.map((notification) => (
                <li key={notification.id}>
                  <button
                    aria-label={`${notification.read ? 'Read' : 'Unread'} notification: ${notification.message}`}
                    className={cn(
                      'notification-panel__item grid h-auto w-full justify-start gap-1.5 whitespace-normal rounded-md border-0 bg-transparent px-3 py-2 text-left shadow-none hover:bg-accent hover:text-accent-foreground',
                      notification.read
                        ? 'notification-panel__item--read font-normal text-muted-foreground'
                        : 'notification-panel__item--unread font-semibold text-foreground',
                    )}
                    onClick={() => void markRead(notification)}
                    type="button"
                  >
                    <span>{notification.message}</span>
                    <time
                      className="text-xs font-normal text-muted-foreground"
                      dateTime={notification.createdAt}
                    >
                      {new Date(notification.createdAt).toLocaleString()}
                    </time>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
