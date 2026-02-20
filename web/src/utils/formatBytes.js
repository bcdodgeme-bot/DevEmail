/**
 * Format byte count into human-readable string.
 * formatBytes(1024) → "1.0 KB"
 */
export function formatBytes(bytes, decimals = 1) {
  if (bytes == null || bytes === 0) return '0 B';

  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return `${(bytes / Math.pow(k, i)).toFixed(decimals)} ${sizes[i]}`;
}
