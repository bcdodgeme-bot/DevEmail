import { Trash2 } from 'lucide-react';
import styles from './Placeholder.module.css';

export default function Trash() {
  return (
    <div className={styles.container}>
      <div className={styles.center}>
        <div className={styles.iconWrap}><Trash2 size={32} strokeWidth={1.5} /></div>
        <h2 className={styles.title}>Trash</h2>
        <p className={styles.subtitle}>Trashed messages will appear here</p>
        <p className={styles.meta}>Phase 2</p>
      </div>
    </div>
  );
}
