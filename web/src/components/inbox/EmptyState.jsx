import { Mail, Send, FileEdit, Trash2, Users, Megaphone } from 'lucide-react';
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

const CATEGORY_EMPTY_CONFIG = {
  people: {
    icon: Users,
    title: 'No people messages',
    subtitle: 'Mail from your contacts will appear here. Right-click any message and move it here to teach the classifier.',
  },
  bulk: {
    icon: Megaphone,
    title: 'No bulk messages yet',
    subtitle: 'Newsletters, transactional mail, and notifications land here. Right-click any newsletter to move it — the classifier learns from each move.',
  },
};

/**
 * Empty / placeholder state for the right-hand detail pane.
 *
 * Props:
 *   view            – inbox | sent | drafts | trash.
 *   listIsEmpty     – when true and view==='inbox', show a category-aware
 *                     empty message instead of the default "select a
 *                     conversation" prompt. The user has nothing to select.
 *   activeCategory  – 'people' | 'bulk' | null/'all'. Drives copy.
 */
export default function EmptyState({ view = 'inbox', listIsEmpty = false, activeCategory = null }) {
  let config;
  if (view === 'inbox' && listIsEmpty && (activeCategory === 'people' || activeCategory === 'bulk')) {
    config = CATEGORY_EMPTY_CONFIG[activeCategory];
  } else {
    config = VIEW_CONFIG[view] || VIEW_CONFIG.inbox;
  }
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
