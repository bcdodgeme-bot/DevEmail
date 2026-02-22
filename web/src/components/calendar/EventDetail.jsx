import {
  Calendar,
  Clock,
  MapPin,
  AlignLeft,
  Repeat,
  Edit3,
  Trash2,
  X,
} from 'lucide-react';
import { format } from 'date-fns';
import styles from './EventDetail.module.css';

export default function EventDetail({
  event,
  calendar,
  onEdit,
  onDelete,
  onClose,
}) {
  if (!event) {
    return (
      <div className={styles.container}>
        <div className={styles.empty}>Select an event to view details</div>
      </div>
    );
  }

  const startDate = new Date(event.start_at);
  const endDate = event.end_at ? new Date(event.end_at) : null;

  const formatEventTime = () => {
    if (event.all_day) return 'All day';
    let str = format(startDate, 'h:mm a');
    if (endDate) str += ` – ${format(endDate, 'h:mm a')}`;
    return str;
  };

  const calColor = calendar?.color || 'var(--accent-purple)';

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerTop}>
          <span className={styles.colorDot} style={{ background: calColor }} />
          <div className={styles.headerActions}>
            <button
              className={styles.actionBtn}
              onClick={() => onEdit(event)}
              title="Edit event"
              type="button"
            >
              <Edit3 size={14} />
            </button>
            <button
              className={`${styles.actionBtn} ${styles.deleteBtn}`}
              onClick={() => onDelete(event.id)}
              title="Delete event"
              type="button"
            >
              <Trash2 size={14} />
            </button>
            <button
              className={styles.actionBtn}
              onClick={onClose}
              title="Close"
              type="button"
            >
              <X size={14} />
            </button>
          </div>
        </div>
        <h2 className={styles.title}>{event.title}</h2>
      </div>

      {/* Content */}
      <div className={styles.content}>
        {/* Date */}
        <div className={styles.field}>
          <Calendar size={14} className={styles.fieldIcon} />
          <div className={styles.fieldContent}>
            <span className={styles.fieldPrimary}>
              {format(startDate, 'EEEE, MMMM d, yyyy')}
            </span>
            {endDate && !event.all_day && (
              <span className={styles.fieldSecondary}>
                {format(endDate, 'EEEE, MMMM d, yyyy')}
              </span>
            )}
          </div>
        </div>

        {/* Time */}
        <div className={styles.field}>
          <Clock size={14} className={styles.fieldIcon} />
          <span className={styles.fieldPrimary}>{formatEventTime()}</span>
        </div>

        {/* Location */}
        {event.location && (
          <div className={styles.field}>
            <MapPin size={14} className={styles.fieldIcon} />
            <span className={styles.fieldPrimary}>{event.location}</span>
          </div>
        )}

        {/* Calendar */}
        {calendar && (
          <div className={styles.field}>
            <span
              className={styles.calDot}
              style={{ background: calColor }}
            />
            <span className={styles.fieldPrimary}>{calendar.name}</span>
          </div>
        )}

        {/* Recurrence */}
        {event.recurrence_rule && (
          <div className={styles.field}>
            <Repeat size={14} className={styles.fieldIcon} />
            <span className={styles.fieldPrimary}>{event.recurrence_rule}</span>
          </div>
        )}

        {/* Description */}
        {event.description && (
          <div className={styles.descSection}>
            <div className={styles.descHeader}>
              <AlignLeft size={14} className={styles.fieldIcon} />
              <span className={styles.descLabel}>Description</span>
            </div>
            <p className={styles.description}>{event.description}</p>
          </div>
        )}

        {/* Meta */}
        <div className={styles.meta}>
          <span>Created: {format(new Date(event.created_at), 'MMM d, yyyy')}</span>
          {event.updated_at && (
            <span>Updated: {format(new Date(event.updated_at), 'MMM d, yyyy')}</span>
          )}
        </div>
      </div>
    </div>
  );
}
