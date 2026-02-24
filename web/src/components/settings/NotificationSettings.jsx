import { useState, useEffect } from 'react';
import { Bell, BellOff, Calendar, Clock, Save } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import styles from './NotificationSettings.module.css';

export default function NotificationSettings() {
  const [prefs, setPrefs] = useState({
    notify_new_email: true,
    notify_calendar_reminder: true,
    reminder_minutes_before: 15,
    quiet_hours_start: '',
    quiet_hours_end: '',
  });
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadPrefs();
  }, []);

  const loadPrefs = async () => {
    setIsLoading(true);
    try {
      const data = await apiFetch('/preferences/notifications');
      setPrefs({
        notify_new_email: data.notify_new_email ?? true,
        notify_calendar_reminder: data.notify_calendar_reminder ?? true,
        reminder_minutes_before: data.reminder_minutes_before ?? 15,
        quiet_hours_start: data.quiet_hours_start || '',
        quiet_hours_end: data.quiet_hours_end || '',
      });
    } catch {
      // Use defaults on error
    } finally {
      setIsLoading(false);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);
    setSaved(false);
    try {
      const data = await apiFetch('/preferences/notifications', {
        method: 'PUT',
        body: JSON.stringify(prefs),
      });
      setPrefs({
        notify_new_email: data.notify_new_email,
        notify_calendar_reminder: data.notify_calendar_reminder,
        reminder_minutes_before: data.reminder_minutes_before,
        quiet_hours_start: data.quiet_hours_start || '',
        quiet_hours_end: data.quiet_hours_end || '',
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err.message || 'Failed to save preferences');
    } finally {
      setIsSaving(false);
    }
  };

  const update = (key, value) => {
    setPrefs((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  };

  if (isLoading) {
    return <div className={styles.loading}>Loading preferences...</div>;
  }

  return (
    <div className={styles.container}>
      <h3 className={styles.title}>Notifications</h3>
      <p className={styles.subtitle}>Configure when and how you receive notifications</p>

      <div className={styles.section}>
        <div className={styles.toggle}>
          <div className={styles.toggleInfo}>
            <Bell size={16} />
            <div>
              <span className={styles.toggleLabel}>New email notifications</span>
              <span className={styles.toggleDesc}>Get notified when new emails arrive</span>
            </div>
          </div>
          <button
            className={`${styles.switch} ${prefs.notify_new_email ? styles.switchOn : ''}`}
            onClick={() => update('notify_new_email', !prefs.notify_new_email)}
            type="button"
            role="switch"
            aria-checked={prefs.notify_new_email}
          >
            <span className={styles.switchThumb} />
          </button>
        </div>

        <div className={styles.toggle}>
          <div className={styles.toggleInfo}>
            <Calendar size={16} />
            <div>
              <span className={styles.toggleLabel}>Calendar reminders</span>
              <span className={styles.toggleDesc}>Get reminders before calendar events</span>
            </div>
          </div>
          <button
            className={`${styles.switch} ${prefs.notify_calendar_reminder ? styles.switchOn : ''}`}
            onClick={() => update('notify_calendar_reminder', !prefs.notify_calendar_reminder)}
            type="button"
            role="switch"
            aria-checked={prefs.notify_calendar_reminder}
          >
            <span className={styles.switchThumb} />
          </button>
        </div>

        {prefs.notify_calendar_reminder && (
          <div className={styles.field}>
            <label className={styles.fieldLabel}>Remind me</label>
            <select
              className={styles.fieldSelect}
              value={prefs.reminder_minutes_before}
              onChange={(e) => update('reminder_minutes_before', parseInt(e.target.value))}
            >
              <option value={5}>5 minutes before</option>
              <option value={10}>10 minutes before</option>
              <option value={15}>15 minutes before</option>
              <option value={30}>30 minutes before</option>
              <option value={60}>1 hour before</option>
            </select>
          </div>
        )}
      </div>

      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <Clock size={16} />
          <span>Quiet hours</span>
        </div>
        <p className={styles.sectionDesc}>
          Pause notifications during these hours
        </p>
        <div className={styles.timeRow}>
          <div className={styles.timeField}>
            <label className={styles.fieldLabel}>From</label>
            <input
              className={styles.fieldInput}
              type="time"
              value={prefs.quiet_hours_start}
              onChange={(e) => update('quiet_hours_start', e.target.value)}
            />
          </div>
          <div className={styles.timeField}>
            <label className={styles.fieldLabel}>To</label>
            <input
              className={styles.fieldInput}
              type="time"
              value={prefs.quiet_hours_end}
              onChange={(e) => update('quiet_hours_end', e.target.value)}
            />
          </div>
        </div>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      <button
        className={styles.saveBtn}
        onClick={handleSave}
        disabled={isSaving}
        type="button"
      >
        <Save size={14} />
        <span>{isSaving ? 'Saving...' : saved ? 'Saved!' : 'Save preferences'}</span>
      </button>
    </div>
  );
}
