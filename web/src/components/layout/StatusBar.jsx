import { Wifi, WifiOff, RefreshCw, Clock } from 'lucide-react';
import { format } from 'date-fns';
import styles from './StatusBar.module.css';

export default function StatusBar({
  isConnected = true,
  isSyncing = false,
  lastSynced = null,
  accountCount = 0,
}) {
  const now = format(new Date(), 'h:mm a');

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
        {lastSynced && !isSyncing && (
          <span className={styles.meta}>
            Last synced {lastSynced}
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
