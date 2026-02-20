// Deterministic color palette for avatars
const AVATAR_COLORS = [
  '#6366f1', // indigo
  '#8b5cf6', // violet
  '#a855f7', // purple
  '#d946ef', // fuchsia
  '#ec4899', // pink
  '#f43f5e', // rose
  '#ef4444', // red
  '#f97316', // orange
  '#f59e0b', // amber
  '#eab308', // yellow
  '#84cc16', // lime
  '#22c55e', // green
  '#14b8a6', // teal
  '#06b6d4', // cyan
  '#3b82f6', // blue
  '#2563eb', // blue-dark
];

function hashString(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return Math.abs(hash);
}

export function getAvatarColor(identifier) {
  const hash = hashString(identifier.toLowerCase());
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

export function getAvatarStyle(identifier) {
  const color = getAvatarColor(identifier);
  return {
    backgroundColor: color,
  };
}

/**
 * Get a CSS gradient string for an avatar background.
 * Used by NavRail for the user avatar.
 */
export function getAvatarGradient(identifier) {
  const hash = hashString(identifier.toLowerCase());
  const color1 = AVATAR_COLORS[hash % AVATAR_COLORS.length];
  const color2 = AVATAR_COLORS[(hash + 3) % AVATAR_COLORS.length];
  return `linear-gradient(135deg, ${color1}, ${color2})`;
}

export function getInitials(name) {
  if (!name) return '?';

  // If it's an email address, use the first letter
  if (name.includes('@')) {
    return name[0].toUpperCase();
  }

  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) {
    return parts[0][0]?.toUpperCase() || '?';
  }
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
