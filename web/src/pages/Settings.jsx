import { Settings as SettingsIcon } from 'lucide-react';
import styles from './Placeholder.module.css';

export default function SettingsPage() {
  return (
    <div className={styles.container}>
      <div className={styles.center}>
        <div className={styles.iconWrap}><SettingsIcon size={32} strokeWidth={1.5} /></div>
        <h2 className={styles.title}>Settings</h2>
        <p className={styles.subtitle}>Account management and preferences</p>
        <p className={styles.meta}>Phase 6</p>
      </div>
    </div>
  );
}
