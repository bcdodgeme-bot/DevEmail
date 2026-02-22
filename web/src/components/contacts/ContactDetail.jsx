import {
  Mail,
  Phone,
  MapPin,
  Globe,
  Building2,
  Briefcase,
  Star,
  Edit3,
  Trash2,
  Calendar,
  Clock,
  Tag,
  ExternalLink,
} from 'lucide-react';
import { getInitials, getAvatarGradient } from '../../utils/avatarColor';
import { formatDate } from '../../utils/formatDate';
import styles from './ContactDetail.module.css';

export default function ContactDetail({
  contact,
  status,
  onEdit,
  onDelete,
  onToggleFavorite,
  onComposeEmail,
}) {
  if (status === 'loading') {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>Loading contact...</div>
      </div>
    );
  }

  if (!contact) {
    return (
      <div className={styles.container}>
        <div className={styles.empty}>Select a contact to view details</div>
      </div>
    );
  }

  const displayName =
    contact.display_name ||
    `${contact.first_name || ''} ${contact.last_name || ''}`.trim() ||
    'Unknown';

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerTop}>
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
          <div className={styles.headerActions}>
            <button
              className={`${styles.actionBtn} ${contact.is_favorite ? styles.starActive : ''}`}
              onClick={() => onToggleFavorite(contact.id)}
              title={contact.is_favorite ? 'Remove from favorites' : 'Add to favorites'}
              type="button"
            >
              <Star
                size={16}
                fill={contact.is_favorite ? 'var(--accent-amber)' : 'none'}
                strokeWidth={contact.is_favorite ? 0 : 1.5}
              />
            </button>
            <button
              className={styles.actionBtn}
              onClick={onEdit}
              title="Edit contact"
              type="button"
            >
              <Edit3 size={16} />
            </button>
            <button
              className={`${styles.actionBtn} ${styles.deleteBtn}`}
              onClick={() => onDelete(contact.id)}
              title="Delete contact"
              type="button"
            >
              <Trash2 size={16} />
            </button>
          </div>
        </div>

        <h2 className={styles.name}>{displayName}</h2>
        {contact.headline && (
          <p className={styles.headline}>{contact.headline}</p>
        )}
        {(contact.job_title || contact.company) && (
          <p className={styles.role}>
            {contact.job_title}
            {contact.job_title && contact.company && ' at '}
            {contact.company}
          </p>
        )}
      </div>

      {/* Content */}
      <div className={styles.content}>
        {/* Emails */}
        {contact.emails?.length > 0 && (
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>
              <Mail size={14} /> Email
            </h3>
            {contact.emails.map((email, i) => (
              <div key={i} className={styles.fieldRow}>
                <span className={styles.fieldType}>{email.type}</span>
                <a
                  href={`mailto:${email.address}`}
                  className={styles.fieldLink}
                  onClick={(e) => {
                    e.preventDefault();
                    onComposeEmail(email.address, displayName);
                  }}
                >
                  {email.address}
                </a>
              </div>
            ))}
          </section>
        )}

        {/* Phones */}
        {contact.phones?.length > 0 && (
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>
              <Phone size={14} /> Phone
            </h3>
            {contact.phones.map((phone, i) => (
              <div key={i} className={styles.fieldRow}>
                <span className={styles.fieldType}>{phone.type}</span>
                <a href={`tel:${phone.number}`} className={styles.fieldLink}>
                  {phone.number}
                </a>
              </div>
            ))}
          </section>
        )}

        {/* Company / Department */}
        {(contact.company || contact.department) && (
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>
              <Building2 size={14} /> Organization
            </h3>
            {contact.company && (
              <div className={styles.fieldRow}>
                <span className={styles.fieldType}>Company</span>
                <span className={styles.fieldValue}>{contact.company}</span>
              </div>
            )}
            {contact.department && (
              <div className={styles.fieldRow}>
                <span className={styles.fieldType}>Department</span>
                <span className={styles.fieldValue}>{contact.department}</span>
              </div>
            )}
            {contact.job_title && (
              <div className={styles.fieldRow}>
                <span className={styles.fieldType}>Title</span>
                <span className={styles.fieldValue}>{contact.job_title}</span>
              </div>
            )}
          </section>
        )}

        {/* Location / Addresses */}
        {(contact.location || contact.addresses?.length > 0) && (
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>
              <MapPin size={14} /> Location
            </h3>
            {contact.location && (
              <div className={styles.fieldRow}>
                <span className={styles.fieldValue}>{contact.location}</span>
              </div>
            )}
            {contact.addresses?.map((addr, i) => (
              <div key={i} className={styles.fieldRow}>
                <span className={styles.fieldType}>{addr.type}</span>
                <span className={styles.fieldValue}>
                  {[addr.street, addr.city, addr.state, addr.postal_code, addr.country]
                    .filter(Boolean)
                    .join(', ')}
                </span>
              </div>
            ))}
          </section>
        )}

        {/* Websites & Social */}
        {(contact.websites?.length > 0 || contact.social_profiles?.length > 0) && (
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>
              <Globe size={14} /> Web & Social
            </h3>
            {contact.websites?.map((url, i) => (
              <div key={`w-${i}`} className={styles.fieldRow}>
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={styles.fieldLink}
                >
                  {url.replace(/^https?:\/\//, '')} <ExternalLink size={10} />
                </a>
              </div>
            ))}
            {contact.social_profiles?.map((sp, i) => (
              <div key={`s-${i}`} className={styles.fieldRow}>
                <span className={styles.fieldType}>{sp.platform}</span>
                <a
                  href={sp.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={styles.fieldLink}
                >
                  {sp.url.replace(/^https?:\/\//, '')} <ExternalLink size={10} />
                </a>
              </div>
            ))}
          </section>
        )}

        {/* Tags */}
        {contact.tags?.length > 0 && (
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>
              <Tag size={14} /> Tags
            </h3>
            <div className={styles.tags}>
              {contact.tags.map((tag) => (
                <span key={tag} className={styles.tag}>{tag}</span>
              ))}
            </div>
          </section>
        )}

        {/* Notes */}
        {contact.notes && (
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>Notes</h3>
            <p className={styles.notes}>{contact.notes}</p>
          </section>
        )}

        {/* Meta */}
        <section className={styles.meta}>
          {contact.last_interaction_at && (
            <span>
              <Clock size={11} /> Last interaction: {formatDate(contact.last_interaction_at)}
            </span>
          )}
          {contact.source && (
            <span>Source: {contact.source}</span>
          )}
          {contact.created_at && (
            <span>Added: {formatDate(contact.created_at)}</span>
          )}
        </section>
      </div>
    </div>
  );
}
