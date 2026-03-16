/**
 * Browser notification helpers.
 * Permission is requested once when the user logs in.
 * Reminders are fired from NotificationBell polling.
 */

export function requestBrowserNotificationPermission() {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
  }
}

export function canShowBrowserNotifications() {
  return 'Notification' in window && Notification.permission === 'granted';
}

export function showBrowserNotification(title, body) {
  if (!canShowBrowserNotifications()) return;
  new Notification(title, { body: body || undefined, icon: '/favicon.ico' });
}
