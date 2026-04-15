import { useState, useEffect } from 'react';
import { Plus, Trash2, Copy, X, AlertTriangle, Check } from 'lucide-react';
import { apiKeysAPI } from '../../api/apiKeys';
import styles from './ApiKeysSettings.module.css';

function formatDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function ApiKeysSettings() {
  const [keys, setKeys] = useState([]);
  const [status, setStatus] = useState('idle'); // idle | loading | ready | failed
  const [error, setError] = useState(null);

  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);

  // Shown once in a modal after create
  const [revealedKey, setRevealedKey] = useState(null);
  const [copied, setCopied] = useState(false);

  const load = async () => {
    setStatus('loading');
    setError(null);
    try {
      const data = await apiKeysAPI.list();
      setKeys(data);
      setStatus('ready');
    } catch (err) {
      setError(err.message || 'Failed to load API keys');
      setStatus('failed');
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const result = await apiKeysAPI.create(newName.trim());
      setRevealedKey(result);
      setNewName('');
      await load();
    } catch (err) {
      setError(err.message || 'Failed to create API key');
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (id, name) => {
    if (!window.confirm(`Revoke "${name}"? Any tool using this key will stop working immediately.`)) {
      return;
    }
    try {
      await apiKeysAPI.revoke(id);
      setKeys((prev) => prev.filter((k) => k.id !== id));
    } catch (err) {
      setError(err.message || 'Failed to revoke key');
    }
  };

  const handleCopy = async () => {
    if (!revealedKey?.key) return;
    try {
      await navigator.clipboard.writeText(revealedKey.key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignore
    }
  };

  const closeReveal = () => {
    setRevealedKey(null);
    setCopied(false);
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h3 className={styles.title}>API Keys</h3>
        <p className={styles.subtitle}>
          Keys grant full account access to internal tools. Treat them like passwords.
        </p>
      </div>

      {/* Create form */}
      <form className={styles.createForm} onSubmit={handleCreate}>
        <input
          className={styles.nameInput}
          type="text"
          placeholder="Key name (e.g. Syntax Prime)"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          maxLength={100}
          disabled={creating}
        />
        <button
          className={styles.createBtn}
          type="submit"
          disabled={creating || !newName.trim()}
        >
          <Plus size={14} />
          <span>{creating ? 'Generating…' : 'Generate key'}</span>
        </button>
      </form>

      {error && <div className={styles.error}>{error}</div>}

      {/* Key list */}
      {status === 'loading' && <div className={styles.loading}>Loading…</div>}
      {status === 'ready' && keys.length === 0 && (
        <div className={styles.empty}>No API keys yet.</div>
      )}
      {status === 'ready' && keys.length > 0 && (
        <div className={styles.list}>
          {keys.map((k) => (
            <div key={k.id} className={styles.row}>
              <div className={styles.rowMain}>
                <div className={styles.rowName}>{k.name}</div>
                <div className={styles.rowPrefix}>{k.prefix}…</div>
              </div>
              <div className={styles.rowMeta}>
                <span>Created {formatDate(k.created_at)}</span>
                <span>Last used {formatDate(k.last_used_at)}</span>
              </div>
              <button
                className={styles.revokeBtn}
                onClick={() => handleRevoke(k.id, k.name)}
                title="Revoke key"
                type="button"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Reveal modal */}
      {revealedKey && (
        <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && closeReveal()}>
          <div className={styles.modal}>
            <div className={styles.modalHeader}>
              <h4 className={styles.modalTitle}>API key created</h4>
              <button className={styles.closeBtn} onClick={closeReveal} type="button">
                <X size={16} />
              </button>
            </div>

            <div className={styles.warning}>
              <AlertTriangle size={16} />
              <span>
                Copy this key now. It will <strong>never</strong> be shown again — if you lose it,
                revoke it and generate a new one.
              </span>
            </div>

            <div className={styles.keyDisplay}>
              <code className={styles.keyText}>{revealedKey.key}</code>
              <button className={styles.copyBtn} onClick={handleCopy} type="button">
                {copied ? <Check size={14} /> : <Copy size={14} />}
                <span>{copied ? 'Copied' : 'Copy'}</span>
              </button>
            </div>

            <div className={styles.modalFooter}>
              <button className={styles.doneBtn} onClick={closeReveal} type="button">
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
