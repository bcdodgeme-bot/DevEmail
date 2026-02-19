import { FileEdit } from 'lucide-react';
import styles from './Placeholder.module.css';

export default function Drafts() {
  return (
    <div className={styles.container}>
      <div className={styles.center}>
        <div className={styles.iconWrap}><FileEdit size={32} strokeWidth={1.5} /></div>
        <h2 className={styles.title}>Drafts</h2>
        <p className={styles.subtitle}>Draft messages will appear here</p>
        <p className={styles.meta}>Phase 3</p>
      </div>
    </div>
  );
}
