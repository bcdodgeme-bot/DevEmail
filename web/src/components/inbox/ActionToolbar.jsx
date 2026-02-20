import { useDispatch } from 'react-redux';
import {
  Reply,
  Forward,
  Archive,
  Trash2,
  Star,
  MailOpen,
  MailX,
} from 'lucide-react';
import {
  toggleStar,
  archiveThread,
  trashThread,
  markUnread,
} from '../../store/inboxSlice';
import styles from './ActionToolbar.module.css';

export default function ActionToolbar({ thread }) {
  const dispatch = useDispatch();

  if (!thread) return null;

  const actions = [
    {
      key: 'reply',
      icon: Reply,
      label: 'Reply',
      onClick: () => {
        /* TODO: open compose in reply mode */
      },
    },
    {
      key: 'forward',
      icon: Forward,
      label: 'Forward',
      onClick: () => {
        /* TODO: open compose in forward mode */
      },
    },
    { key: 'divider1' },
    {
      key: 'star',
      icon: Star,
      label: thread.is_starred ? 'Unstar' : 'Star',
      active: thread.is_starred,
      onClick: () => dispatch(toggleStar(thread.id)),
    },
    {
      key: 'unread',
      icon: MailX,
      label: 'Mark unread',
      onClick: () => dispatch(markUnread(thread.id)),
    },
    {
      key: 'archive',
      icon: Archive,
      label: 'Archive',
      onClick: () => dispatch(archiveThread(thread.id)),
    },
    {
      key: 'trash',
      icon: Trash2,
      label: 'Delete',
      danger: true,
      onClick: () => dispatch(trashThread(thread.id)),
    },
  ];

  return (
    <div className={styles.toolbar}>
      {actions.map((action) =>
        action.key.startsWith('divider') ? (
          <div key={action.key} className={styles.divider} />
        ) : (
          <button
            key={action.key}
            className={`${styles.btn} ${action.active ? styles.active : ''} ${action.danger ? styles.danger : ''}`}
            onClick={action.onClick}
            title={action.label}
          >
            <action.icon size={16} fill={action.active && action.key === 'star' ? '#f59e0b' : 'none'} />
            <span className={styles.label}>{action.label}</span>
          </button>
        )
      )}
    </div>
  );
}
