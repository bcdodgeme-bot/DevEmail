/**
 * Format bytes into a human-readable string.
 * 1024 → "1 KB", 1048576 → "1 MB"
 */
export function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';

  const units = ['B', 'KB', 'MB', 'GB'];
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const value = bytes / Math.pow(k, i);

  return `${value % 1 === 0 ? value : value.toFixed(1)} ${units[i]}`;
}
