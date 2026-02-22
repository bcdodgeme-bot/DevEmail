/**
 * Avatar color and initials utilities.
 * Used by AccountPicker, ContactListItem, ContactDetail, etc.
 */

const GRADIENTS = [
  'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
  'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
  'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
  'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)',
  'linear-gradient(135deg, #fa709a 0%, #fee140 100%)',
  'linear-gradient(135deg, #a18cd1 0%, #fbc2eb 100%)',
  'linear-gradient(135deg, #fccb90 0%, #d57eeb 100%)',
  'linear-gradient(135deg, #e0c3fc 0%, #8ec5fc 100%)',
  'linear-gradient(135deg, #f5576c 0%, #ff6f61 100%)',
  'linear-gradient(135deg, #89f7fe 0%, #66a6ff 100%)',
  'linear-gradient(135deg, #fddb92 0%, #d1fdff 100%)',
  'linear-gradient(135deg, #9890e3 0%, #b1f4cf 100%)',
];

/**
 * Simple hash function for strings.
 */
function hashString(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash |= 0; // Convert to 32bit integer
  }
  return Math.abs(hash);
}

/**
 * Get a deterministic gradient based on a string (email, name, etc).
 */
export function getAvatarGradient(str) {
  if (!str) return GRADIENTS[0];
  const idx = hashString(str) % GRADIENTS.length;
  return GRADIENTS[idx];
}

/**
 * Extract initials from a name or email.
 * "John Doe" → "JD"
 * "john@example.com" → "J"
 */
export function getInitials(str) {
  if (!str) return '?';

  // If it's an email, use first letter
  if (str.includes('@')) {
    return str.charAt(0).toUpperCase();
  }

  const parts = str.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
  }
  return parts[0].charAt(0).toUpperCase();
}
