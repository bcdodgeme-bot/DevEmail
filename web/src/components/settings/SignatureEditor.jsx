import { useState, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { Plus, Trash2, Edit3, Save, X, Check } from 'lucide-react';
import DOMPurify from 'dompurify';
import { selectAccounts, fetchAccounts } from '../../store/accountsSlice';
import { accountsAPI } from '../../api/accounts';
import styles from './SignatureEditor.module.css';

function sanitizeHtml(html) {
  if (!html) return '';
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      'a', 'b', 'i', 'u', 'em', 'strong', 'p', 'br', 'div', 'span',
      'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'table', 'thead', 'tbody', 'tr', 'td', 'th',
      'img', 'blockquote', 'pre', 'code', 'hr', 'sub', 'sup',
      'font', 'center', 'small',
    ],
    ALLOWED_ATTR: [
      'href', 'src', 'alt', 'title', 'style', 'class', 'width', 'height',
      'target', 'rel', 'color', 'size', 'face', 'align', 'valign',
      'bgcolor', 'border', 'cellpadding', 'cellspacing', 'colspan', 'rowspan',
    ],
    ALLOW_DATA_ATTR: false,
    ADD_ATTR: ['target'],
  });
}

export default function SignatureEditor() {
  const dispatch = useDispatch();
  const accounts = useSelector(selectAccounts);

  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [signatures, setSignatures] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [editingId, setEditingId] = useState(null); // null = not editing, 'new' = creating
  const [form, setForm] = useState({ name: '', body_html: '', is_default: false });
  const [error, setError] = useState(null);

  /* Select first account by default */
  useEffect(() => {
    if (accounts.length > 0 && !selectedAccountId) {
      setSelectedAccountId(accounts[0].id);
    }
  }, [accounts, selectedAccountId]);

  /* Load signatures when account changes */
  useEffect(() => {
    if (!selectedAccountId) return;
    loadSignatures();
  }, [selectedAccountId]);

  const loadSignatures = async () => {
    setIsLoading(true);
    try {
      const data = await accountsAPI.getSignatures(selectedAccountId);
      setSignatures(data.signatures || data || []);
    } catch {
      setSignatures([]);
    } finally {
      setIsLoading(false);
    }
  };

  /* Start editing */
  const startEdit = (sig) => {
    setEditingId(sig.id);
    setForm({ name: sig.name, body_html: sig.body_html || '', is_default: sig.is_default });
    setError(null);
  };

  /* Start creating */
  const startNew = () => {
    setEditingId('new');
    setForm({ name: '', body_html: '', is_default: false });
    setError(null);
  };

  /* Cancel */
  const cancelEdit = () => {
    setEditingId(null);
    setForm({ name: '', body_html: '', is_default: false });
    setError(null);
  };

  /* Save */
  const handleSave = async () => {
    if (!form.name.trim()) {
      setError('Signature name is required');
      return;
    }
    setError(null);
    try {
      if (editingId === 'new') {
        await accountsAPI.createSignature(selectedAccountId, form);
      } else {
        await accountsAPI.updateSignature(selectedAccountId, editingId, form);
      }
      cancelEdit();
      loadSignatures();
      dispatch(fetchAccounts()); // refresh accounts store so compose picks up changes
    } catch (err) {
      setError(err.message || 'Failed to save signature');
    }
  };

  /* Delete */
  const handleDelete = async (sigId) => {
    if (!window.confirm('Delete this signature?')) return;
    try {
      await accountsAPI.deleteSignature(selectedAccountId, sigId);
      loadSignatures();
      dispatch(fetchAccounts());
    } catch (err) {
      setError(err.message || 'Failed to delete');
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h3 className={styles.title}>Email Signatures</h3>
        <p className={styles.subtitle}>
          Create signatures for each email account
        </p>
      </div>

      {/* Account selector */}
      <div className={styles.accountPicker}>
        <label className={styles.pickerLabel}>Account:</label>
        <select
          className={styles.pickerSelect}
          value={selectedAccountId}
          onChange={(e) => setSelectedAccountId(e.target.value)}
        >
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.email_address}
            </option>
          ))}
        </select>
      </div>

      {/* Signature list */}
      <div className={styles.sigList}>
        {isLoading && <div className={styles.loading}>Loading...</div>}

        {!isLoading && signatures.length === 0 && editingId !== 'new' && (
          <div className={styles.empty}>No signatures for this account</div>
        )}

        {signatures.map((sig) =>
          editingId === sig.id ? (
            /* Editing form inline */
            <div key={sig.id} className={styles.editCard}>
              {renderForm()}
            </div>
          ) : (
            <div key={sig.id} className={styles.sigCard}>
              <div className={styles.sigHeader}>
                <span className={styles.sigName}>
                  {sig.name}
                  {sig.is_default && <span className={styles.defaultTag}>Default</span>}
                </span>
                <div className={styles.sigActions}>
                  <button
                    className={styles.sigBtn}
                    onClick={() => startEdit(sig)}
                    title="Edit"
                    type="button"
                  >
                    <Edit3 size={12} />
                  </button>
                  <button
                    className={`${styles.sigBtn} ${styles.sigDeleteBtn}`}
                    onClick={() => handleDelete(sig.id)}
                    title="Delete"
                    type="button"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
              <div
                className={styles.sigPreview}
                dangerouslySetInnerHTML={{ __html: sanitizeHtml(sig.body_html || sig.body_text || '') }}
              />
            </div>
          )
        )}

        {/* New signature form */}
        {editingId === 'new' && (
          <div className={styles.editCard}>{renderForm()}</div>
        )}
      </div>

      {/* Add button */}
      {editingId === null && (
        <button className={styles.addBtn} onClick={startNew} type="button">
          <Plus size={14} /> Add Signature
        </button>
      )}

      {error && <div className={styles.error}>{error}</div>}
    </div>
  );

  function renderForm() {
    return (
      <div className={styles.form}>
        <div className={styles.formRow}>
          <input
            className={styles.formInput}
            type="text"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Signature name"
            autoFocus
          />
          <label className={styles.checkLabel}>
            <input
              type="checkbox"
              checked={form.is_default}
              onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
              className={styles.checkbox}
            />
            Default
          </label>
        </div>
        <textarea
          className={styles.formTextarea}
          value={form.body_html}
          onChange={(e) => setForm({ ...form, body_html: e.target.value })}
          placeholder="Signature content (HTML supported)..."
          rows={5}
        />
        <div className={styles.formActions}>
          <button className={styles.saveBtn} onClick={handleSave} type="button">
            <Save size={12} /> Save
          </button>
          <button className={styles.cancelBtn} onClick={cancelEdit} type="button">
            <X size={12} /> Cancel
          </button>
        </div>
      </div>
    );
  }
}
