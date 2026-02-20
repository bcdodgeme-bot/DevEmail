/**
 * Generate a consistent gradient background for user avatars.
 * Same name always produces the same gradient.
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
  'linear-gradient(135deg, #f5576c 0%, #ff8a5c 100%)',
  'linear-gradient(135deg, #667eea 0%, #43e97b 100%)',
  'linear-gradient(135deg, #6a11cb 0%, #2575fc 100%)',
  'linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%)',
];

function hashString(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash |= 0;
  }
  return Math.abs(hash);
}

export function getInitials(name, address) {
  if (name) {
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    return name[0].toUpperCase();
  }
  if (address) return address[0].toUpperCase();
  return '?';
}

export function getAvatarGradient(name) {
  if (!name) return GRADIENTS[0];
  const index = hashString(name) % GRADIENTS.length;
  return GRADIENTS[index];
}
