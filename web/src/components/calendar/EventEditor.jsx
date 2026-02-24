import { useState, useEffect } from 'react';
import { X, Save, Repeat } from 'lucide-react';
import { format } from 'date-fns';
import styles from './EventEditor.module.css';

const RECURRENCE_PRESETS = [
  { label: 'Does not repeat', value: '' },
  { label: 'Every day', value: 'RRULE:FREQ=DAILY' },
  { label: 'Every weekday (Mon–Fri)', value: 'RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR' },
  { label: 'Every week', value: 'RRULE:FREQ=WEEKLY' },
  { label: 'Every 2 weeks', value: 'RRULE:FREQ=WEEKLY;INTERVAL=2' },
  { label: 'Every month', value: 'RRULE:FREQ=MONTHLY' },
  { label: 'Every year', value: 'RRULE:FREQ=YEARLY' },
  { label: 'Custom...', value: '__custom__' },
];

/**
 * Convert an RRULE string to a human-readable label (client-side fallback).
 * The backend also returns recurrence_human, but this is for the editor.
 */
function rruleToLabel(rrule) {
  if (!rrule) return 'Does not repeat';
  const preset = RECURRENCE_PRESETS.find((p) => p.value === rrule);
  if (preset) return preset.label;

  // Parse simple patterns
  const parts = {};
  const rule = rrule.replace(/^RRULE:/i, '');
  rule.split(';').forEach((seg) => {
    const [k, v] = seg.split('=');
    if (k && v) parts[k.toUpperCase()] = v;
  });

  const freq = parts.FREQ || '';
  const interval = parseInt(parts.INTERVAL || '1');
  const byday = parts.BYDAY || '';

  const dayNames = { MO: 'Mon', TU: 'Tue', WE: 'Wed', TH: 'Thu', FR: 'Fri', SA: 'Sat', SU: 'Sun' };

  let base = '';
  if (freq === 'DAILY') base = interval === 1 ? 'Every day' : `Every ${interval} days`;
  else if (freq === 'WEEKLY') {
    base = interval === 1 ? 'Every week' : `Every ${interval} weeks`;
    if (byday) {
      const days = byday.split(',').map((d) => dayNames[d.trim()] || d).join(', ');
      base += ` on ${days}`;
    }
  } else if (freq === 'MONTHLY') base = interval === 1 ? 'Every month' : `Every ${interval} months`;
  else if (freq === 'YEARLY') base = interval === 1 ? 'Every year' : `Every ${interval} years`;
  else return rrule;

  if (parts.COUNT) base += `, ${parts.COUNT} times`;
  if (parts.UNTIL) base += `, until ${parts.UNTIL.substring(0, 8)}`;

  return base;
}

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
    recurrence_rule: '',
  });
  const [showCustomRecurrence, setShowCustomRecurrence] = useState(false);
  const [customFreq, setCustomFreq] = useState('WEEKLY');
  const [customInterval, setCustomInterval] = useState(1);
  const [customDays, setCustomDays] = useState([]);
  const [customEnd, setCustomEnd] = useState('never');
  const [customCount, setCustomCount] = useState(10);
  const [customUntil, setCustomUntil] = useState('');

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
        recurrence_rule: event.recurrence_rule || '',
      });
    } else {
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
        recurrence_rule: '',
      });
    }
  }, [event, calendars, defaultDate]);

  const updateField = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleRecurrenceChange = (value) => {
    if (value === '__custom__') {
      setShowCustomRecurrence(true);
    } else {
      setShowCustomRecurrence(false);
      updateField('recurrence_rule', value);
    }
  };

  const buildCustomRrule = () => {
    let rule = `RRULE:FREQ=${customFreq}`;
    if (customInterval > 1) rule += `;INTERVAL=${customInterval}`;
    if (customFreq === 'WEEKLY' && customDays.length > 0) {
      rule += `;BYDAY=${customDays.join(',')}`;
    }
    if (customEnd === 'count') rule += `;COUNT=${customCount}`;
    if (customEnd === 'until' && customUntil) {
      rule += `;UNTIL=${customUntil.replace(/-/g, '')}T235959Z`;
    }
    return rule;
  };

  const applyCustomRecurrence = () => {
    const rule = buildCustomRrule();
    updateField('recurrence_rule', rule);
    setShowCustomRecurrence(false);
  };

  const toggleDay = (day) => {
    setCustomDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day]
    );
  };

  const handleSubmit = () => {
    if (!form.title.trim()) return;
    if (!form.calendar_id) return;

    const payload = {
      ...form,
      start_at: new Date(form.start_at).toISOString(),
      end_at: form.end_at ? new Date(form.end_at).toISOString() : null,
      recurrence_rule: form.recurrence_rule || null,
    };

    onSave(payload);
  };

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

  const DAYS = [
    { code: 'MO', label: 'M' },
    { code: 'TU', label: 'T' },
    { code: 'WE', label: 'W' },
    { code: 'TH', label: 'T' },
    { code: 'FR', label: 'F' },
    { code: 'SA', label: 'S' },
    { code: 'SU', label: 'S' },
  ];

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <h3 className={styles.headerTitle}>
            {event ? 'Edit Event' : 'New Event'}
          </h3>
          <button className={styles.closeBtn} onClick={onClose} type="button">
            <X size={16} />
          </button>
        </div>

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

          <div className={styles.field}>
            <label className={styles.label}>Calendar</label>
            <select
              className={styles.select}
              value={form.calendar_id}
              onChange={(e) => updateField('calendar_id', e.target.value)}
            >
              {(calendars || []).map((cal) => (
                <option key={cal.id} value={cal.id}>{cal.name}</option>
              ))}
            </select>
          </div>

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

          {/* Recurrence */}
          <div className={styles.field}>
            <label className={styles.label}>
              <Repeat size={14} style={{ marginRight: 4, verticalAlign: 'middle' }} />
              Repeat
            </label>
            <select
              className={styles.select}
              value={
                RECURRENCE_PRESETS.find((p) => p.value === form.recurrence_rule)
                  ? form.recurrence_rule
                  : form.recurrence_rule
                    ? '__custom__'
                    : ''
              }
              onChange={(e) => handleRecurrenceChange(e.target.value)}
            >
              {RECURRENCE_PRESETS.map((preset) => (
                <option key={preset.value} value={preset.value}>
                  {preset.label}
                </option>
              ))}
            </select>
            {form.recurrence_rule && !showCustomRecurrence && (
              <span className={styles.recurrenceHint}>
                {rruleToLabel(form.recurrence_rule)}
              </span>
            )}
          </div>

          {/* Custom recurrence builder */}
          {showCustomRecurrence && (
            <div className={styles.customRecurrence}>
              <div className={styles.customRow}>
                <label className={styles.label}>Every</label>
                <input
                  className={styles.numberInput}
                  type="number"
                  min={1}
                  max={99}
                  value={customInterval}
                  onChange={(e) => setCustomInterval(parseInt(e.target.value) || 1)}
                />
                <select
                  className={styles.select}
                  value={customFreq}
                  onChange={(e) => setCustomFreq(e.target.value)}
                >
                  <option value="DAILY">day(s)</option>
                  <option value="WEEKLY">week(s)</option>
                  <option value="MONTHLY">month(s)</option>
                  <option value="YEARLY">year(s)</option>
                </select>
              </div>

              {customFreq === 'WEEKLY' && (
                <div className={styles.dayPicker}>
                  {DAYS.map(({ code, label }) => (
                    <button
                      key={code}
                      className={`${styles.dayBtn} ${customDays.includes(code) ? styles.dayBtnActive : ''}`}
                      onClick={() => toggleDay(code)}
                      type="button"
                    >
                      {label}
                    </button>
                  ))}
                </div>
              )}

              <div className={styles.customRow}>
                <label className={styles.label}>Ends</label>
                <select
                  className={styles.select}
                  value={customEnd}
                  onChange={(e) => setCustomEnd(e.target.value)}
                >
                  <option value="never">Never</option>
                  <option value="count">After N occurrences</option>
                  <option value="until">On date</option>
                </select>
              </div>

              {customEnd === 'count' && (
                <div className={styles.customRow}>
                  <label className={styles.label}>Occurrences</label>
                  <input
                    className={styles.numberInput}
                    type="number"
                    min={1}
                    max={999}
                    value={customCount}
                    onChange={(e) => setCustomCount(parseInt(e.target.value) || 1)}
                  />
                </div>
              )}

              {customEnd === 'until' && (
                <div className={styles.customRow}>
                  <label className={styles.label}>Until</label>
                  <input
                    className={styles.input}
                    type="date"
                    value={customUntil}
                    onChange={(e) => setCustomUntil(e.target.value)}
                  />
                </div>
              )}

              <button
                className={styles.applyBtn}
                onClick={applyCustomRecurrence}
                type="button"
              >
                Apply
              </button>
            </div>
          )}

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
