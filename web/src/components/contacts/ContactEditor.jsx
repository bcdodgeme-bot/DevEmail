import { useState, useEffect } from 'react';
import { Save, X, Plus, Trash2 } from 'lucide-react';
import styles from './ContactEditor.module.css';

/**
 * Inline contact editor form.
 * contact = existing ContactDetailResponse or null for new
 * onSave = (formData) => void
 * onCancel = () => void
 */
export default function ContactEditor({ contact, onSave, onCancel }) {
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    display_name: '',
    company: '',
    job_title: '',
    department: '',
    headline: '',
    location: '',
    birthday: '',
    notes: '',
    is_favorite: false,
    emails: [{ type: 'work', address: '' }],
    phones: [{ type: 'work', number: '' }],
    tags: [],
    websites: [],
  });

  const [tagInput, setTagInput] = useState('');

  /* Populate form from existing contact */
  useEffect(() => {
    if (contact) {
      setForm({
        first_name: contact.first_name || '',
        last_name: contact.last_name || '',
        display_name: contact.display_name || '',
        company: contact.company || '',
        job_title: contact.job_title || '',
        department: contact.department || '',
        headline: contact.headline || '',
        location: contact.location || '',
        birthday: contact.birthday || '',
        notes: contact.notes || '',
        is_favorite: contact.is_favorite || false,
        emails:
          contact.emails?.length > 0
            ? contact.emails.map((e) => ({ ...e }))
            : [{ type: 'work', address: '' }],
        phones:
          contact.phones?.length > 0
            ? contact.phones.map((p) => ({ ...p }))
            : [{ type: 'work', number: '' }],
        tags: contact.tags ? [...contact.tags] : [],
        websites: contact.websites ? [...contact.websites] : [],
      });
    }
  }, [contact]);

  const updateField = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  /* Email array helpers */
  const updateEmail = (index, field, value) => {
    const next = [...form.emails];
    next[index] = { ...next[index], [field]: value };
    setForm((prev) => ({ ...prev, emails: next }));
  };
  const addEmail = () => {
    setForm((prev) => ({ ...prev, emails: [...prev.emails, { type: 'work', address: '' }] }));
  };
  const removeEmail = (index) => {
    setForm((prev) => ({ ...prev, emails: prev.emails.filter((_, i) => i !== index) }));
  };

  /* Phone array helpers */
  const updatePhone = (index, field, value) => {
    const next = [...form.phones];
    next[index] = { ...next[index], [field]: value };
    setForm((prev) => ({ ...prev, phones: next }));
  };
  const addPhone = () => {
    setForm((prev) => ({ ...prev, phones: [...prev.phones, { type: 'work', number: '' }] }));
  };
  const removePhone = (index) => {
    setForm((prev) => ({ ...prev, phones: prev.phones.filter((_, i) => i !== index) }));
  };

  /* Tag helpers */
  const addTag = () => {
    const trimmed = tagInput.trim();
    if (trimmed && !form.tags.includes(trimmed)) {
      setForm((prev) => ({ ...prev, tags: [...prev.tags, trimmed] }));
    }
    setTagInput('');
  };
  const removeTag = (tag) => {
    setForm((prev) => ({ ...prev, tags: prev.tags.filter((t) => t !== tag) }));
  };

  /* Submit */
  const handleSubmit = () => {
    const cleaned = {
      ...form,
      emails: form.emails.filter((e) => e.address.trim()),
      phones: form.phones.filter((p) => p.number.trim()),
    };
    onSave(cleaned);
  };

  return (
    <div className={styles.editor}>
      <div className={styles.header}>
        <h3 className={styles.title}>
          {contact ? 'Edit Contact' : 'New Contact'}
        </h3>
        <div className={styles.headerActions}>
          <button className={styles.cancelBtn} onClick={onCancel} type="button">
            <X size={14} /> Cancel
          </button>
          <button className={styles.saveBtn} onClick={handleSubmit} type="button">
            <Save size={14} /> Save
          </button>
        </div>
      </div>

      <div className={styles.form}>
        {/* Name */}
        <div className={styles.row}>
          <div className={styles.field}>
            <label className={styles.label}>First Name</label>
            <input
              className={styles.input}
              value={form.first_name}
              onChange={(e) => updateField('first_name', e.target.value)}
              placeholder="First"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Last Name</label>
            <input
              className={styles.input}
              value={form.last_name}
              onChange={(e) => updateField('last_name', e.target.value)}
              placeholder="Last"
            />
          </div>
        </div>

        <div className={styles.field}>
          <label className={styles.label}>Display Name</label>
          <input
            className={styles.input}
            value={form.display_name}
            onChange={(e) => updateField('display_name', e.target.value)}
            placeholder="Display name"
          />
        </div>

        {/* Company */}
        <div className={styles.row}>
          <div className={styles.field}>
            <label className={styles.label}>Company</label>
            <input
              className={styles.input}
              value={form.company}
              onChange={(e) => updateField('company', e.target.value)}
              placeholder="Company"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Job Title</label>
            <input
              className={styles.input}
              value={form.job_title}
              onChange={(e) => updateField('job_title', e.target.value)}
              placeholder="Title"
            />
          </div>
        </div>

        {/* Emails */}
        <div className={styles.arraySection}>
          <label className={styles.label}>Email Addresses</label>
          {form.emails.map((email, i) => (
            <div key={i} className={styles.arrayRow}>
              <select
                className={styles.typeSelect}
                value={email.type}
                onChange={(e) => updateEmail(i, 'type', e.target.value)}
              >
                <option value="work">Work</option>
                <option value="personal">Personal</option>
                <option value="other">Other</option>
              </select>
              <input
                className={styles.input}
                value={email.address}
                onChange={(e) => updateEmail(i, 'address', e.target.value)}
                placeholder="email@example.com"
                type="email"
              />
              {form.emails.length > 1 && (
                <button
                  className={styles.removeBtn}
                  onClick={() => removeEmail(i)}
                  type="button"
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          ))}
          <button className={styles.addRowBtn} onClick={addEmail} type="button">
            <Plus size={12} /> Add email
          </button>
        </div>

        {/* Phones */}
        <div className={styles.arraySection}>
          <label className={styles.label}>Phone Numbers</label>
          {form.phones.map((phone, i) => (
            <div key={i} className={styles.arrayRow}>
              <select
                className={styles.typeSelect}
                value={phone.type}
                onChange={(e) => updatePhone(i, 'type', e.target.value)}
              >
                <option value="work">Work</option>
                <option value="mobile">Mobile</option>
                <option value="home">Home</option>
                <option value="other">Other</option>
              </select>
              <input
                className={styles.input}
                value={phone.number}
                onChange={(e) => updatePhone(i, 'number', e.target.value)}
                placeholder="(555) 123-4567"
                type="tel"
              />
              {form.phones.length > 1 && (
                <button
                  className={styles.removeBtn}
                  onClick={() => removePhone(i)}
                  type="button"
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          ))}
          <button className={styles.addRowBtn} onClick={addPhone} type="button">
            <Plus size={12} /> Add phone
          </button>
        </div>

        {/* Location */}
        <div className={styles.field}>
          <label className={styles.label}>Location</label>
          <input
            className={styles.input}
            value={form.location}
            onChange={(e) => updateField('location', e.target.value)}
            placeholder="City, State"
          />
        </div>

        {/* Tags */}
        <div className={styles.arraySection}>
          <label className={styles.label}>Tags</label>
          <div className={styles.tagList}>
            {form.tags.map((tag) => (
              <span key={tag} className={styles.tag}>
                {tag}
                <button
                  className={styles.tagRemove}
                  onClick={() => removeTag(tag)}
                  type="button"
                >
                  <X size={10} />
                </button>
              </span>
            ))}
          </div>
          <div className={styles.arrayRow}>
            <input
              className={styles.input}
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); addTag(); }
              }}
              placeholder="Add tag..."
            />
            <button className={styles.addRowBtn} onClick={addTag} type="button">
              <Plus size={12} />
            </button>
          </div>
        </div>

        {/* Notes */}
        <div className={styles.field}>
          <label className={styles.label}>Notes</label>
          <textarea
            className={styles.textarea}
            value={form.notes}
            onChange={(e) => updateField('notes', e.target.value)}
            placeholder="Notes about this contact..."
            rows={4}
          />
        </div>
      </div>
    </div>
  );
}
