import {
  formatDistanceToNowStrict,
  format,
  isToday,
  isYesterday,
  isThisYear,
} from 'date-fns';

/**
 * Format a date for thread list display.
 * - < 1 hour: "3m"
 * - Today: "2:30 PM"
 * - Yesterday: "Yesterday"
 * - This year: "Feb 19"
 * - Older: "Feb 19, 2025"
 */
export function formatThreadDate(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now - date;
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 60) {
    return `${Math.max(1, diffMin)}m`;
  }

  if (isToday(date)) {
    return format(date, 'h:mm a');
  }

  if (isYesterday(date)) {
    return 'Yesterday';
  }

  if (isThisYear(date)) {
    return format(date, 'MMM d');
  }

  return format(date, 'MMM d, yyyy');
}

/**
 * Format a date for message detail view.
 * "Feb 19, 2026 at 2:30 PM"
 */
export function formatMessageDate(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return format(date, "MMM d, yyyy 'at' h:mm a");
}

/**
 * Format relative time for status bar.
 * "2 minutes ago"
 */
export function formatRelativeTime(dateStr) {
  if (!dateStr) return 'Never';
  const date = new Date(dateStr);
  return formatDistanceToNowStrict(date, { addSuffix: true });
}
