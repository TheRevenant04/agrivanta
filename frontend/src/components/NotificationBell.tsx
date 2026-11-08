import { useCallback, useEffect, useRef, useState } from 'react';
import { useServices } from '../services/servicesContext';
import type { Notification } from '../services/types';
import './NotificationBell.css';

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
    <div className="notification-bell">
      <button
        aria-label={`Notifications${unreadCount ? `, ${unreadCount} unread` : ''}`}
        aria-expanded={isOpen}
        aria-controls="notification-panel"
        className="notification-bell__toggle"
        onClick={togglePanel}
        type="button"
      >
        <svg
          aria-hidden="true"
          className="notification-bell__icon"
          viewBox="0 0 24 24"
        >
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />
        </svg>
        <span>Notifications</span>
        {unreadCount > 0 && (
          <span
            aria-label={`${unreadCount} unread notifications`}
            className="notification-bell__badge"
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>
      {isOpen && (
        <section
          aria-label="Notifications"
          className="notification-panel"
          id="notification-panel"
        >
          <h2>Notifications</h2>
          {isLoading ? (
            <p role="status">Loading notifications…</p>
          ) : hasError ? (
            <div>
              <p role="alert">Unable to load notifications.</p>
              <button onClick={() => void refreshNotifications()} type="button">
                Try again
              </button>
            </div>
          ) : notifications.length === 0 ? (
            <p>No notifications yet.</p>
          ) : (
            <ul className="notification-panel__list">
              {notifications.map((notification) => (
                <li key={notification.id}>
                  <button
                    aria-label={`${notification.read ? 'Read' : 'Unread'} notification: ${notification.message}`}
                    className={`notification-panel__item ${
                      notification.read
                        ? 'notification-panel__item--read'
                        : 'notification-panel__item--unread'
                    }`}
                    onClick={() => void markRead(notification)}
                    type="button"
                  >
                    <span>{notification.message}</span>
                    <time dateTime={notification.createdAt}>
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
