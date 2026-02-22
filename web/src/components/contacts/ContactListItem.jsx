import { Star } from 'lucide-react';
import { getInitials, getAvatarGradient } from '../../utils/avatarColor';
import styles from './ContactListItem.module.css';

export default function ContactListItem({ contact, isSelected, onSelect, onToggleFavorite }) {
  const displayName =
    contact.display_name ||
    `${contact.first_name || ''} ${contact.last_name || ''}`.trim() ||
    contact.emails?.[0]?.address ||
    'Unknown';

  const primaryEmail = contact.emails?.[0]?.address;

  return (
    <button
      className={`${styles.item} ${isSelected ? styles.selected : ''}`}
      onClick={() => onSelect(contact.id)}
      type="button"
    >
      <span
        className={styles.avatar}
        style={{ background: getAvatarGradient(displayName) }}
      >
        {contact.avatar_url ? (
          <img src={contact.avatar_url} alt="" className={styles.avatarImg} />
        ) : (
          getInitials(displayName)
        )}
      </span>

      <span className={styles.info}>
        <span className={styles.name}>{displayName}</span>
        {contact.company && (
          <span className={styles.company}>{contact.company}</span>
        )}
        {primaryEmail && (
          <span className={styles.email}>{primaryEmail}</span>
        )}
      </span>

      <button
        className={`${styles.star} ${contact.is_favorite ? styles.starActive : ''}`}
        onClick={(e) => {
          e.stopPropagation();
          onToggleFavorite(contact.id);
        }}
        title={contact.is_favorite ? 'Remove from favorites' : 'Add to favorites'}
        type="button"
      >
        <Star
          size={14}
          fill={contact.is_favorite ? 'var(--accent-amber)' : 'none'}
          strokeWidth={contact.is_favorite ? 0 : 1.5}
        />
      </button>
    </button>
  );
}
