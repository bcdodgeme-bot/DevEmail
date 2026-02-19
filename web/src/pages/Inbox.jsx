import { Mail } from 'lucide-react';
import styles from './Placeholder.module.css';

export default function Inbox() {
  return (
    <div className={styles.container}>
      <div className={styles.center}>
        <div className={styles.iconWrap}>
          <Mail size={32} strokeWidth={1.5} />
        </div>
        <h2 className={styles.title}>Inbox</h2>
        <p className={styles.subtitle}>Your unified inbox will appear here</p>
        <p className={styles.meta}>Phase 2 — Coming next</p>
      </div>
    </div>
  );
}
