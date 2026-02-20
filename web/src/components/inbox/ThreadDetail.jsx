import ActionToolbar from './ActionToolbar';
import MessageBubble from './MessageBubble';
import styles from './ThreadDetail.module.css';

export default function ThreadDetail({ thread, status }) {
  if (status === 'loading' || !thread) {
    return (
      <div className={styles.loading}>
        <div className={styles.loader} />
      </div>
    );
  }

  return (
    <div className={styles.detail}>
      {/* Header */}
      <div className={styles.header}>
        <h2 className={styles.subject}>{thread.subject || '(no subject)'}</h2>
        <span className={styles.msgCount}>
          {thread.message_count} message{thread.message_count !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Action toolbar */}
      <ActionToolbar thread={thread} />

      {/* Messages */}
      <div className={styles.messages}>
        {thread.messages?.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
      </div>
    </div>
  );
}
