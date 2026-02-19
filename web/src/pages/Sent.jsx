// Sent.jsx
import { Send } from 'lucide-react';
import styles from './Placeholder.module.css';

export default function Sent() {
  return (
    <div className={styles.container}>
      <div className={styles.center}>
        <div className={styles.iconWrap}><Send size={32} strokeWidth={1.5} /></div>
        <h2 className={styles.title}>Sent</h2>
        <p className={styles.subtitle}>Sent messages will appear here</p>
        <p className={styles.meta}>Phase 2</p>
      </div>
    </div>
  );
}
