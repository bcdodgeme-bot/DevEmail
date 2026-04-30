import { useEffect, useState } from 'react';
import styles from './MoveCategoryModal.module.css';

function extractDomain(address) {
  if (!address || typeof address !== 'string') return null;
  const at = address.lastIndexOf('@');
  if (at < 0) return null;
  return address.slice(at + 1).trim().toLowerCase() || null;
}

/**
 * Confirmation modal for the manual-move action.
 *
 *   <MoveCategoryModal
 *     open={!!moveTarget}
 *     fromAddress={moveTarget?.fromAddress}
 *     targetCategory="bulk"
 *     onCancel={() => setMoveTarget(null)}
 *     onConfirm={async ({ applyToDomain, applyToExisting }) => { ... }}
 *   />
 */
export default function MoveCategoryModal({
  open,
  fromAddress,
  targetCategory,           // 'people' | 'bulk'
  onCancel,
  onConfirm,
}) {
  const [applyToDomain, setApplyToDomain] = useState(false);
  const [applyToExisting, setApplyToExisting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // Reset state when the modal opens for a new message.
  useEffect(() => {
    if (open) {
      setApplyToDomain(false);
      setApplyToExisting(false);
      setError(null);
      setSubmitting(false);
    }
  }, [open, fromAddress, targetCategory]);

  // Escape closes the modal.
  useEffect(() => {
    if (!open) return;
    const handleKey = (e) => {
      if (e.key === 'Escape' && !submitting) onCancel();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [open, submitting, onCancel]);

  if (!open) return null;

  const domain = extractDomain(fromAddress);
  const targetLabel = targetCategory === 'bulk' ? 'Bulk' : 'People';

  const handleConfirm = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm({ applyToDomain, applyToExisting });
    } catch (e) {
      setError(e?.message || 'Could not move message. Please try again.');
      setSubmitting(false);
    }
    // On success the parent unmounts the modal, so no need to clear submitting.
  };

  return (
    <div className={styles.backdrop} role="dialog" aria-modal="true" aria-label={`Move to ${targetLabel}`}>
      <div className={styles.modal}>
        <h3 className={styles.title}>Move to {targetLabel}</h3>
        <p className={styles.body}>
          This message will be moved to <strong>{targetLabel}</strong>. By default, this only
          affects this message.
        </p>
        <div className={styles.from}>
          <span className={styles.fromLabel}>From:</span>{' '}
          <span className={styles.fromAddress}>{fromAddress || 'unknown'}</span>
        </div>

        <div className={styles.checkboxes}>
          <label className={[styles.checkboxRow, !domain ? styles.disabled : ''].filter(Boolean).join(' ')}>
            <input
              type="checkbox"
              checked={applyToDomain}
              disabled={!domain || submitting}
              onChange={(e) => setApplyToDomain(e.target.checked)}
            />
            <span>
              Apply to entire <strong>@{domain || '…'}</strong>
            </span>
          </label>

          <label className={styles.checkboxRow}>
            <input
              type="checkbox"
              checked={applyToExisting}
              disabled={submitting}
              onChange={(e) => setApplyToExisting(e.target.checked)}
            />
            <span>Apply to existing messages from this sender</span>
          </label>
        </div>

        {error && (
          <div className={styles.error} role="alert">
            {error}
          </div>
        )}

        <div className={styles.actions}>
          <button
            type="button"
            className={styles.cancelBtn}
            onClick={onCancel}
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            type="button"
            className={styles.confirmBtn}
            onClick={handleConfirm}
            disabled={submitting}
          >
            {submitting ? 'Moving…' : `Move to ${targetLabel}`}
          </button>
        </div>
      </div>
    </div>
  );
}
