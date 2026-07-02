// Route paths
export const ROUTES = {
  LOGIN: '/login',
  OAUTH_CALLBACK: '/auth/callback',
  INBOX: '/',
  SENT: '/sent',
  DRAFTS: '/drafts',
  TRASH: '/trash',
  SPAM: '/spam',
  CONTACTS: '/contacts',
  CALENDAR: '/calendar',
  SETTINGS: '/settings',
};

// Keyboard shortcut mappings
export const SHORTCUTS = {
  NAVIGATE_DOWN: 'j',
  NAVIGATE_UP: 'k',
  OPEN_THREAD: 'Enter',
  CLOSE_PANEL: 'Escape',
  ARCHIVE: 'e',
  TRASH: '#',
  STAR: 's',
  REPLY: 'r',
  REPLY_ALL: 'a',
  FORWARD: 'f',
  COMPOSE: 'c',
  COMMAND_PALETTE: 'k', // With Cmd/Ctrl
  SEARCH: '/',
  SELECT: 'x',
};

// Snooze presets
export const SNOOZE_OPTIONS = [
  { label: 'Later today', hours: 3 },
  { label: 'Tomorrow', hours: 24 },
  { label: 'Next week', hours: 168 },
  { label: 'Custom...', hours: null },
];

// Polling interval for inbox refresh (ms)
export const POLL_INTERVAL = 30000; // 30 seconds
