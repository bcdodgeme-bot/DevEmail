import { useState, useRef, useEffect } from 'react';
import { useDispatch } from 'react-redux';
import {
  Reply,
  ReplyAll,
  Forward,
  Archive,
  Trash2,
  Star,
  MailX,
  Clock,
  ShieldAlert,
} from 'lucide-react';
import {
  toggleStar,
  archiveThread,
  trashThread,
  markThreadSpam,
  markUnread,
  snoozeThread,
  unsnoozeThread,
} from '../../store/inboxSlice';
import { SNOOZE_OPTIONS } from '../../utils/constants';
import styles from './ActionToolbar.module.css';

export default function ActionToolbar({ thread }) {
  const dispatch = useDispatch();
  const [showSnoozeMenu, setShowSnoozeMenu] = useState(false);
  const snoozeRef = useRef(null);

  // Close snooze menu on outside click
  useEffect(() => {
    if (!showSnoozeMenu) return;
    function handleClickOutside(e) {
      if (snoozeRef.current && !snoozeRef.current.contains(e.target)) {
        setShowSnoozeMenu(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showSnoozeMenu]);

  if (!thread) return null;

  const handleReply = () => {
    window.dispatchEvent(
      new CustomEvent('devemail:compose', {
        detail: { replyTo: thread },
      })
    );
  };

  const handleReplyAll = () => {
    window.dispatchEvent(
      new CustomEvent('devemail:compose', {
        detail: { replyTo: thread, replyAll: true },
      })
    );
  };

  const handleForward = () => {
    window.dispatchEvent(
      new CustomEvent('devemail:compose', {
        detail: { forward: thread },
      })
    );
  };

  const handleSnooze = (hours) => {
    if (hours === null) {
      // Custom — for now just snooze 24h as a fallback
      // A date picker could be wired up here later
      hours = 24;
    }
    const snoozedUntil = new Date(Date.now() + hours * 60 * 60 * 1000).toISOString();
    dispatch(snoozeThread({ threadId: thread.id, snoozedUntil }));
    setShowSnoozeMenu(false);
  };

  const handleUnsnooze = () => {
    dispatch(unsnoozeThread(thread.id));
  };

  return (
    <div className={styles.toolbar}>
      <button className={styles.btn} onClick={handleReply} title="Reply">
        <Reply size={16} />
        <span className={styles.label}>Reply</span>
      </button>

      <button className={styles.btn} onClick={handleReplyAll} title="Reply All">
        <ReplyAll size={16} />
        <span className={styles.label}>Reply All</span>
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

      {/* Snooze */}
      <div className={styles.snoozeWrap} ref={snoozeRef}>
        {thread.is_snoozed ? (
          <button
            className={`${styles.btn} ${styles.active}`}
            onClick={handleUnsnooze}
            title="Unsnooze"
          >
            <Clock size={16} />
            <span className={styles.label}>Unsnooze</span>
          </button>
        ) : (
          <button
            className={styles.btn}
            onClick={() => setShowSnoozeMenu(!showSnoozeMenu)}
            title="Snooze"
          >
            <Clock size={16} />
            <span className={styles.label}>Snooze</span>
          </button>
        )}

        {showSnoozeMenu && (
          <div className={styles.snoozeMenu}>
            {SNOOZE_OPTIONS.map((option) => (
              <button
                key={option.label}
                className={styles.snoozeOption}
                onClick={() => handleSnooze(option.hours)}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>
        )}
      </div>

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
        className={styles.btn}
        onClick={() => dispatch(markThreadSpam(thread.id))}
        title="Mark as spam — move to Junk"
      >
        <ShieldAlert size={16} />
        <span className={styles.label}>Spam</span>
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
