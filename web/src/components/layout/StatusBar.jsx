import { useEffect, useState } from 'react';
import { Wifi, WifiOff, RefreshCw, Clock } from 'lucide-react';
import { format } from 'date-fns';
import styles from './StatusBar.module.css';

/** Human-readable elapsed time since an ISO timestamp. */
function formatSince(iso) {
  if (!iso) return null;
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(iso).toLocaleDateString();
}

export default function StatusBar({
  isConnected = true,
  isSyncing = false,
  lastSynced = null,
  accountCount = 0,
}) {
  const now = format(new Date(), 'h:mm a');

  // Tick once per second so the "X seconds ago" label stays fresh
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const syncedLabel = formatSince(lastSynced);

  return (
    <footer className={styles.bar}>
      <div className={styles.left}>
        {/* Connection status */}
        <span className={`${styles.indicator} ${isConnected ? styles.online : styles.offline}`}>
          {isConnected ? (
            <Wifi size={12} />
          ) : (
            <WifiOff size={12} />
          )}
          <span>{isConnected ? 'Connected' : 'Offline'}</span>
        </span>

        {/* Sync status */}
        {isSyncing && (
          <span className={styles.syncing}>
            <RefreshCw size={12} className={styles.spinIcon} />
            <span>Syncing...</span>
          </span>
        )}

        {/* Last synced */}
        {syncedLabel && !isSyncing && (
          <span className={styles.meta} title={new Date(lastSynced).toLocaleString()}>
            Last synced {syncedLabel}
          </span>
        )}
      </div>

      <div className={styles.center}>
        <span className={styles.brand}>DevEmail</span>
        <span className={styles.dot}>·</span>
        <span className={styles.meta}>Syntax Network</span>
      </div>

      <div className={styles.right}>
        {accountCount > 0 && (
          <span className={styles.meta}>
            {accountCount} account{accountCount !== 1 ? 's' : ''}
          </span>
        )}
        <span className={styles.clock}>
          <Clock size={12} />
          <span>{now}</span>
        </span>
      </div>
    </footer>
  );
}
