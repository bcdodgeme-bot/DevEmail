import { useState, useEffect, useRef, useCallback } from 'react';
import { Bell, Check, CheckCheck, Mail, Calendar } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { canShowBrowserNotifications, showBrowserNotification } from '../../utils/browserNotifications';
import styles from './NotificationBell.module.css';

const CATEGORY_ICONS = {
  new_email: Mail,
  calendar_reminder: Calendar,
};

const POLL_INTERVAL = 60_000; // 60 seconds

// IDs of notifications already shown as browser popups — persists across re-renders
// but clears on tab close (fine for time-sensitive reminders)
function loadShownIds() {
  try {
    return new Set(JSON.parse(sessionStorage.getItem('browserNotifIds') || '[]'));
  } catch {
    return new Set();
  }
}

function saveShownIds(set) {
  try {
    sessionStorage.setItem('browserNotifIds', JSON.stringify([...set]));
  } catch { /* storage full — not critical */ }
}

export default function NotificationBell() {
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const ref = useRef(null);
  const shownIds = useRef(loadShownIds());

  /* Fetch unread count on interval */
  const fetchUnreadCount = useCallback(async () => {
    try {
      const data = await apiFetch('/notifications/unread');
      setUnreadCount(data.unread || 0);
    } catch {
      // silent fail
    }
  }, []);

  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchUnreadCount]);

  /* Fire browser notifications for new calendar reminders */
  const checkBrowserReminders = useCallback(async () => {
    if (!canShowBrowserNotifications()) return;
    try {
      const data = await apiFetch('/notifications?unread_only=true&category=calendar_reminder&limit=10');
      const reminders = data.notifications || [];
      for (const n of reminders) {
        if (!shownIds.current.has(n.id)) {
          shownIds.current.add(n.id);
          saveShownIds(shownIds.current);
          showBrowserNotification(n.title, n.body);
        }
      }
    } catch {
      // silent fail
    }
  }, []);

  useEffect(() => {
    checkBrowserReminders();
    const interval = setInterval(checkBrowserReminders, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [checkBrowserReminders]);

  /* Fetch full list when dropdown opens */
  const fetchNotifications = async () => {
    setLoading(true);
    try {
      const data = await apiFetch('/notifications?limit=20');
      setNotifications(data.notifications || []);
    } catch {
      // silent fail
    } finally {
      setLoading(false);
    }
  };

  const toggleDropdown = () => {
    const next = !isOpen;
    setIsOpen(next);
    if (next) fetchNotifications();
  };

  /* Mark single as read */
  const markRead = async (id) => {
    try {
      await apiFetch(`/notifications/${id}/read`, { method: 'POST' });
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, read: true } : n))
      );
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch {
      // silent fail
    }
  };

  /* Mark all as read */
  const markAllRead = async () => {
    try {
      await apiFetch('/notifications/read-all', { method: 'POST' });
      setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
      setUnreadCount(0);
    } catch {
      // silent fail
    }
  };

  /* Click outside to close */
  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) {
        setIsOpen(false);
      }
    }
    if (isOpen) document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [isOpen]);

  /* Time ago helper */
  const timeAgo = (isoStr) => {
    if (!isoStr) return '';
    const diff = Date.now() - new Date(isoStr).getTime();
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  };

  return (
    <div className={styles.container} ref={ref}>
      <button
        className={styles.bellBtn}
        onClick={toggleDropdown}
        title="Notifications"
        type="button"
      >
        <Bell size={18} />
        {unreadCount > 0 && (
          <span className={styles.badge}>
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className={styles.dropdown}>
          <div className={styles.dropdownHeader}>
            <span className={styles.dropdownTitle}>Notifications</span>
            {unreadCount > 0 && (
              <button
                className={styles.markAllBtn}
                onClick={markAllRead}
                type="button"
              >
                <CheckCheck size={14} />
                Mark all read
              </button>
            )}
          </div>

          <div className={styles.list}>
            {loading && notifications.length === 0 && (
              <div className={styles.empty}>Loading…</div>
            )}
            {!loading && notifications.length === 0 && (
              <div className={styles.empty}>No notifications</div>
            )}
            {notifications.map((notif) => {
              const Icon = CATEGORY_ICONS[notif.category] || Bell;
              return (
                <div
                  key={notif.id}
                  className={`${styles.item} ${!notif.read ? styles.unread : ''}`}
                  onClick={() => !notif.read && markRead(notif.id)}
                >
                  <div className={styles.itemIcon}>
                    <Icon size={16} />
                  </div>
                  <div className={styles.itemContent}>
                    <span className={styles.itemTitle}>{notif.title}</span>
                    {notif.body && (
                      <span className={styles.itemBody}>{notif.body}</span>
                    )}
                    <span className={styles.itemTime}>{timeAgo(notif.created_at)}</span>
                  </div>
                  {!notif.read && (
                    <div className={styles.unreadDot} />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
