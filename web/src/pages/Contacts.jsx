import { Users } from 'lucide-react';
import styles from './Placeholder.module.css';

export default function Contacts() {
  return (
    <div className={styles.container}>
      <div className={styles.center}>
        <div className={styles.iconWrap}><Users size={32} strokeWidth={1.5} /></div>
        <h2 className={styles.title}>Contacts</h2>
        <p className={styles.subtitle}>8,487 contacts imported and ready</p>
        <p className={styles.meta}>Phase 4</p>
      </div>
    </div>
  );
}
