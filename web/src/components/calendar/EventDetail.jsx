import {
  Calendar,
  Clock,
  MapPin,
  AlignLeft,
  Repeat,
  Edit3,
  Trash2,
  X,
  Users,
  Video,
  User,
  ExternalLink,
  CheckCircle,
  XCircle,
  HelpCircle,
  MinusCircle,
} from 'lucide-react';
import { format } from 'date-fns';
import DOMPurify from 'dompurify';
import styles from './EventDetail.module.css';

/** Map Google Calendar response status to icon + label */
const STATUS_MAP = {
  accepted: { icon: CheckCircle, label: 'Accepted', className: 'statusAccepted' },
  declined: { icon: XCircle, label: 'Declined', className: 'statusDeclined' },
  tentative: { icon: HelpCircle, label: 'Maybe', className: 'statusTentative' },
  needsAction: { icon: MinusCircle, label: 'Pending', className: 'statusPending' },
};

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
  const attendees = event.attendees || [];
  const hasConference = !!event.conference_link;
  const hasOrganizer = event.organizer_name || event.organizer_email;

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerTop}>
          <div className={styles.headerLeft}>
            <span className={styles.colorDot} style={{ background: calColor }} />
            {event.event_status && event.event_status !== 'confirmed' && (
              <span className={styles.statusBadge}>
                {event.event_status}
              </span>
            )}
          </div>
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

        {/* Google Meet / Conference Link */}
        {hasConference && (
          <div className={styles.field}>
            <Video size={14} className={styles.fieldIcon} />
            <a
              href={event.conference_link}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.conferenceLink}
            >
              Join video call
              <ExternalLink size={12} />
            </a>
          </div>
        )}

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

        {/* Organizer */}
        {hasOrganizer && (
          <div className={styles.field}>
            <User size={14} className={styles.fieldIcon} />
            <div className={styles.fieldContent}>
              <span className={styles.fieldPrimary}>
                {event.organizer_name || event.organizer_email}
              </span>
              {event.organizer_name && event.organizer_email && (
                <span className={styles.fieldSecondary}>
                  {event.organizer_email}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Recurrence */}
        {event.recurrence_rule && (
          <div className={styles.field}>
            <Repeat size={14} className={styles.fieldIcon} />
            <span className={styles.fieldPrimary}>
              {event.recurrence_human || event.recurrence_rule}
            </span>
          </div>
        )}

        {/* Attendees */}
        {attendees.length > 0 && (
          <div className={styles.attendeesSection}>
            <div className={styles.attendeesHeader}>
              <Users size={14} className={styles.fieldIcon} />
              <span className={styles.sectionLabel}>
                Attendees ({attendees.length})
              </span>
            </div>
            <ul className={styles.attendeeList}>
              {attendees.map((a, idx) => {
                const statusInfo = STATUS_MAP[a.response_status] || STATUS_MAP.needsAction;
                const StatusIcon = statusInfo.icon;
                return (
                  <li key={idx} className={styles.attendeeItem}>
                    <StatusIcon
                      size={14}
                      className={`${styles.attendeeStatus} ${styles[statusInfo.className]}`}
                    />
                    <div className={styles.attendeeInfo}>
                      <span className={styles.attendeeName}>
                        {a.name || a.email}
                      </span>
                      {a.name && (
                        <span className={styles.attendeeEmail}>{a.email}</span>
                      )}
                    </div>
                    <span className={styles.attendeeLabel}>
                      {statusInfo.label}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {/* Description */}
        {event.description && (
          <div className={styles.descSection}>
            <div className={styles.descHeader}>
              <AlignLeft size={14} className={styles.fieldIcon} />
              <span className={styles.sectionLabel}>Description</span>
            </div>
            <div
              className={styles.description}
              dangerouslySetInnerHTML={{
                __html: DOMPurify.sanitize(event.description, {
                  ALLOWED_TAGS: ['a', 'b', 'strong', 'i', 'em', 'br', 'p', 'ul', 'ol', 'li', 'span'],
                  ALLOWED_ATTR: ['href', 'target', 'rel', 'class'],
                }),
              }}
            />
          </div>
        )}

        {/* View in Google Calendar */}
        {event.html_link && (
          <a
            href={event.html_link}
            target="_blank"
            rel="noopener noreferrer"
            className={styles.googleLink}
          >
            <ExternalLink size={14} />
            View in Google Calendar
          </a>
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
