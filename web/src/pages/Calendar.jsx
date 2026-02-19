import { Calendar as CalendarIcon } from 'lucide-react';
import styles from './Placeholder.module.css';

export default function CalendarPage() {
  return (
    <div className={styles.container}>
      <div className={styles.center}>
        <div className={styles.iconWrap}><CalendarIcon size={32} strokeWidth={1.5} /></div>
        <h2 className={styles.title}>Calendar</h2>
        <p className={styles.subtitle}>Calendar views will appear here</p>
        <p className={styles.meta}>Phase 5</p>
      </div>
    </div>
  );
}
