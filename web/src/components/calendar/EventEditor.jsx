import { useState, useEffect } from 'react';
import { X, Save } from 'lucide-react';
import { format } from 'date-fns';
import styles from './EventEditor.module.css';

/**
 * EventEditor — modal for creating/editing events.
 * event = existing EventResponse or null for new
 * calendars = available calendars
 * defaultDate = pre-selected date for new events
 * onSave = (formData) => void
 * onClose = () => void
 */
export default function EventEditor({
  event,
  calendars,
  defaultDate,
  onSave,
  onClose,
}) {
  const [form, setForm] = useState({
    calendar_id: '',
    title: '',
    description: '',
    location: '',
    start_at: '',
    end_at: '',
    all_day: false,
  });

  /* Populate form */
  useEffect(() => {
    if (event) {
      setForm({
        calendar_id: event.calendar_id || calendars?.[0]?.id || '',
        title: event.title || '',
        description: event.description || '',
        location: event.location || '',
        start_at: event.start_at
          ? format(new Date(event.start_at), "yyyy-MM-dd'T'HH:mm")
          : '',
        end_at: event.end_at
          ? format(new Date(event.end_at), "yyyy-MM-dd'T'HH:mm")
          : '',
        all_day: event.all_day || false,
      });
    } else {
      /* New event — use default date or now */
      const d = defaultDate ? new Date(defaultDate) : new Date();
      const startStr = format(d, "yyyy-MM-dd'T'HH:mm");
      const endD = new Date(d.getTime() + 60 * 60 * 1000);
      const endStr = format(endD, "yyyy-MM-dd'T'HH:mm");

      setForm({
        calendar_id: calendars?.[0]?.id || '',
        title: '',
        description: '',
        location: '',
        start_at: startStr,
        end_at: endStr,
        all_day: false,
      });
    }
  }, [event, calendars, defaultDate]);

  const updateField = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = () => {
    if (!form.title.trim()) return;
    if (!form.calendar_id) return;

    const payload = {
      ...form,
      start_at: new Date(form.start_at).toISOString(),
      end_at: form.end_at ? new Date(form.end_at).toISOString() : null,
    };

    onSave(payload);
  };

  /* Close on Escape */
  useEffect(() => {
    function handleKey(e) {
      if (e.key === 'Escape') onClose();
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        handleSubmit();
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [form]);

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        {/* Header */}
        <div className={styles.header}>
          <h3 className={styles.headerTitle}>
            {event ? 'Edit Event' : 'New Event'}
          </h3>
          <button className={styles.closeBtn} onClick={onClose} type="button">
            <X size={16} />
          </button>
        </div>

        {/* Form */}
        <div className={styles.form}>
          <div className={styles.field}>
            <input
              className={styles.titleInput}
              type="text"
              value={form.title}
              onChange={(e) => updateField('title', e.target.value)}
              placeholder="Event title"
              autoFocus
            />
          </div>

          {/* Calendar */}
          <div className={styles.field}>
            <label className={styles.label}>Calendar</label>
            <select
              className={styles.select}
              value={form.calendar_id}
              onChange={(e) => updateField('calendar_id', e.target.value)}
            >
              {(calendars || []).map((cal) => (
                <option key={cal.id} value={cal.id}>
                  {cal.name}
                </option>
              ))}
            </select>
          </div>

          {/* All day toggle */}
          <div className={styles.checkRow}>
            <label className={styles.checkLabel}>
              <input
                type="checkbox"
                checked={form.all_day}
                onChange={(e) => updateField('all_day', e.target.checked)}
                className={styles.checkbox}
              />
              All day
            </label>
          </div>

          {/* Start / End */}
          <div className={styles.row}>
            <div className={styles.field}>
              <label className={styles.label}>Start</label>
              <input
                className={styles.input}
                type={form.all_day ? 'date' : 'datetime-local'}
                value={form.all_day ? form.start_at.split('T')[0] : form.start_at}
                onChange={(e) => updateField('start_at', e.target.value)}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>End</label>
              <input
                className={styles.input}
                type={form.all_day ? 'date' : 'datetime-local'}
                value={form.all_day ? (form.end_at?.split('T')[0] || '') : form.end_at}
                onChange={(e) => updateField('end_at', e.target.value)}
              />
            </div>
          </div>

          {/* Location */}
          <div className={styles.field}>
            <label className={styles.label}>Location</label>
            <input
              className={styles.input}
              type="text"
              value={form.location}
              onChange={(e) => updateField('location', e.target.value)}
              placeholder="Add location"
            />
          </div>

          {/* Description */}
          <div className={styles.field}>
            <label className={styles.label}>Description</label>
            <textarea
              className={styles.textarea}
              value={form.description}
              onChange={(e) => updateField('description', e.target.value)}
              placeholder="Add description..."
              rows={3}
            />
          </div>
        </div>

        {/* Footer */}
        <div className={styles.footer}>
          <button className={styles.cancelBtn} onClick={onClose} type="button">
            Cancel
          </button>
          <button
            className={styles.saveBtn}
            onClick={handleSubmit}
            disabled={!form.title.trim() || !form.calendar_id}
            type="button"
          >
            <Save size={14} />
            {event ? 'Update' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  );
}
