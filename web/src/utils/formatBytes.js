/**
 * Format bytes into a human-readable string.
 * Examples: "1.2 KB", "3.5 MB", "128 B"
 */
export function formatBytes(bytes) {
  if (bytes === 0 || bytes == null) return '0 B';

  const units = ['B', 'KB', 'MB', 'GB'];
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const size = bytes / Math.pow(k, i);

  return `${size < 10 ? size.toFixed(1) : Math.round(size)} ${units[i] || 'TB'}`;
}
