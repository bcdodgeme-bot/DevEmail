import { useDispatch } from 'react-redux';
import {
  Reply,
  Forward,
  Archive,
  Trash2,
  Star,
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

  const handleReply = () => {
    console.log('Reply clicked, thread:', thread);
    window.dispatchEvent(
      new CustomEvent('devemail:compose', {
        detail: { replyTo: thread },
      })
    );
  };

  const handleForward = () => {
    console.log('Forward clicked, thread:', thread);
    window.dispatchEvent(
      new CustomEvent('devemail:compose', {
        detail: { forward: thread },
      })
    );
  };

  return (
    <div className={styles.toolbar}>
      <button className={styles.btn} onClick={handleReply} title="Reply">
        <Reply size={16} />
        <span className={styles.label}>Reply</span>
      </button>

      <button className={styles.btn} onClick={handleForward} title="Forward">
        <Forward size={16} />
        <span className={styles.label}>Forward</span>
      </button>

      <div className={styles.divider} />

      <button
        className={`${styles.btn} ${thread.is_starred ? styles.active : ''}`}
        onClick={() => dispatch(toggleStar(thread.id))}
        title={thread.is_starred ? 'Unstar' : 'Star'}
      >
        <Star size={16} fill={thread.is_starred ? '#f59e0b' : 'none'} />
        <span className={styles.label}>{thread.is_starred ? 'Unstar' : 'Star'}</span>
      </button>

      <button
        className={styles.btn}
        onClick={() => dispatch(markUnread(thread.id))}
        title="Mark unread"
      >
        <MailX size={16} />
        <span className={styles.label}>Mark unread</span>
      </button>

      <button
        className={styles.btn}
        onClick={() => dispatch(archiveThread(thread.id))}
        title="Archive"
      >
        <Archive size={16} />
        <span className={styles.label}>Archive</span>
      </button>

      <button
        className={`${styles.btn} ${styles.danger}`}
        onClick={() => dispatch(trashThread(thread.id))}
        title="Delete"
      >
        <Trash2 size={16} />
        <span className={styles.label}>Delete</span>
      </button>
    </div>
  );
}
