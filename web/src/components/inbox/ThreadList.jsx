import { Star, Paperclip } from 'lucide-react';
import { useDispatch } from 'react-redux';
import { toggleStar } from '../../store/inboxSlice';
import { getAvatarGradient } from '../../utils/avatarColor';
import { formatRelativeDate } from '../../utils/formatDate';
import styles from './ThreadList.module.css';

function getInitials(name, address) {
  if (name) {
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    return name[0].toUpperCase();
  }
  if (address) return address[0].toUpperCase();
  return '?';
}

function ThreadRow({ thread, isSelected, onSelect, onContextMenu }) {
  const dispatch = useDispatch();

  const initials = getInitials(thread.latest_from_name, thread.latest_from_address);
  const gradient = getAvatarGradient(thread.latest_from_name || thread.latest_from_address || '');
  const displayName = thread.latest_from_name || thread.latest_from_address || 'Unknown';

  const handleStar = (e) => {
    e.stopPropagation();
    dispatch(toggleStar(thread.id));
  };

  const handleContext = (e) => {
    if (!onContextMenu) return;
    e.preventDefault();
    onContextMenu(thread, { x: e.clientX, y: e.clientY });
  };

  return (
    <div
      className={`${styles.row} ${isSelected ? styles.selected : ''} ${thread.has_unread ? styles.unread : ''}`}
      onClick={() => onSelect(thread.id)}
      onContextMenu={handleContext}
      role="button"
      tabIndex={0}
      data-testid="thread-row"
    >
      {/* Avatar */}
      <div className={styles.avatar} style={{ background: gradient }}>
        {initials}
      </div>

      {/* Content */}
      <div className={styles.content}>
        <div className={styles.topRow}>
          <span className={styles.sender}>{displayName}</span>
          <span className={styles.date}>
            {thread.last_message_at ? formatRelativeDate(thread.last_message_at) : ''}
          </span>
        </div>
        <div className={styles.subject}>{thread.subject || '(no subject)'}</div>
        <div className={styles.snippet}>{thread.latest_snippet || ''}</div>
      </div>

      {/* Indicators */}
      <div className={styles.indicators}>
        {thread.has_unread && <div className={styles.unreadDot} />}
        <button
          className={`${styles.starBtn} ${thread.is_starred ? styles.starred : ''}`}
          onClick={handleStar}
          title={thread.is_starred ? 'Unstar' : 'Star'}
        >
          <Star size={14} fill={thread.is_starred ? '#f59e0b' : 'none'} />
        </button>
        {thread.message_count > 1 && (
          <span className={styles.count}>{thread.message_count}</span>
        )}
      </div>
    </div>
  );
}

export default function ThreadList({ threads, status, selectedId, onSelect, onContextMenu }) {
  if (status === 'loading' && threads.length === 0) {
    return (
      <div className={styles.statusWrap}>
        <div className={styles.loader} />
        <span className={styles.statusText}>Loading…</span>
      </div>
    );
  }

  if (status === 'failed') {
    return (
      <div className={styles.statusWrap}>
        <span className={styles.statusText}>Failed to load messages</span>
      </div>
    );
  }

  if (threads.length === 0) {
    return (
      <div className={styles.statusWrap}>
        <span className={styles.statusText}>No messages</span>
      </div>
    );
  }

  return (
    <div className={styles.list}>
      {threads.map((thread) => (
        <ThreadRow
          key={thread.id}
          thread={thread}
          isSelected={thread.id === selectedId}
          onSelect={onSelect}
          onContextMenu={onContextMenu}
        />
      ))}
    </div>
  );
}
