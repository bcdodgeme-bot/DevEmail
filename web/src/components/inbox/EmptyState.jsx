import { Mail, Send, FileEdit, Trash2 } from 'lucide-react';
import styles from './EmptyState.module.css';

const VIEW_CONFIG = {
  inbox: {
    icon: Mail,
    title: 'Select a conversation',
    subtitle: 'Choose a thread from the left to read it here',
  },
  sent: {
    icon: Send,
    title: 'Select a sent message',
    subtitle: 'Choose a thread to view the conversation',
  },
  drafts: {
    icon: FileEdit,
    title: 'Select a draft',
    subtitle: 'Choose a draft to continue editing',
  },
  trash: {
    icon: Trash2,
    title: 'Select a deleted message',
    subtitle: 'Choose a thread to review before permanent deletion',
  },
};

export default function EmptyState({ view = 'inbox' }) {
  const config = VIEW_CONFIG[view] || VIEW_CONFIG.inbox;
  const Icon = config.icon;

  return (
    <div className={styles.container}>
      <div className={styles.center}>
        <div className={styles.iconWrap}>
          <Icon size={32} strokeWidth={1.5} />
        </div>
        <h2 className={styles.title}>{config.title}</h2>
        <p className={styles.subtitle}>{config.subtitle}</p>
      </div>
    </div>
  );
}
