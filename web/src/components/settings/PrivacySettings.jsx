import { useState } from 'react';
import { useDispatch } from 'react-redux';
import { Shield, Download, Trash2, AlertTriangle } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { logout } from '../../store/authSlice';
import styles from './PrivacySettings.module.css';

export default function PrivacySettings() {
  const dispatch = useDispatch();
  const [isExporting, setIsExporting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteInput, setDeleteInput] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState(null);

  const handleExport = async () => {
    setIsExporting(true);
    setError(null);
    try {
      const response = await apiFetch('/preferences/export', {
        method: 'POST',
        raw: true,
      });
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'devemail-export.json';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || 'Export failed');
    } finally {
      setIsExporting(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (deleteInput !== 'DELETE') return;
    setIsDeleting(true);
    setError(null);
    try {
      await apiFetch('/preferences/account', { method: 'DELETE' });
      // Clear local storage and redirect
      dispatch(logout());
    } catch (err) {
      setError(err.message || 'Failed to delete account');
      setIsDeleting(false);
    }
  };

  return (
    <div className={styles.container}>
      <h3 className={styles.title}>Privacy & Security</h3>
      <p className={styles.subtitle}>Manage your data and account security</p>

      {/* Data Export */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <Download size={16} />
          <span>Export your data</span>
        </div>
        <p className={styles.sectionDesc}>
          Download a copy of your account data including contacts, email metadata,
          and settings. Email content is summarized, not fully exported.
        </p>
        <button
          className={styles.actionBtn}
          onClick={handleExport}
          disabled={isExporting}
          type="button"
        >
          <Download size={14} />
          <span>{isExporting ? 'Preparing export...' : 'Download my data'}</span>
        </button>
      </div>

      {/* Account Deletion */}
      <div className={`${styles.section} ${styles.dangerSection}`}>
        <div className={styles.sectionHeader}>
          <AlertTriangle size={16} />
          <span>Delete account</span>
        </div>
        <p className={styles.sectionDesc}>
          Permanently delete your account and all associated data. This includes
          all linked email accounts, contacts, threads, and settings. This action
          cannot be undone.
        </p>

        {!showDeleteConfirm ? (
          <button
            className={styles.dangerBtn}
            onClick={() => setShowDeleteConfirm(true)}
            type="button"
          >
            <Trash2 size={14} />
            <span>Delete my account</span>
          </button>
        ) : (
          <div className={styles.deleteConfirm}>
            <p className={styles.confirmText}>
              Type <strong>DELETE</strong> to confirm permanent account deletion:
            </p>
            <input
              className={styles.confirmInput}
              type="text"
              value={deleteInput}
              onChange={(e) => setDeleteInput(e.target.value)}
              placeholder="Type DELETE"
              autoFocus
            />
            <div className={styles.confirmActions}>
              <button
                className={styles.dangerBtn}
                onClick={handleDeleteAccount}
                disabled={deleteInput !== 'DELETE' || isDeleting}
                type="button"
              >
                {isDeleting ? 'Deleting...' : 'Permanently delete'}
              </button>
              <button
                className={styles.cancelBtn}
                onClick={() => {
                  setShowDeleteConfirm(false);
                  setDeleteInput('');
                }}
                type="button"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {error && <div className={styles.error}>{error}</div>}
    </div>
  );
}
