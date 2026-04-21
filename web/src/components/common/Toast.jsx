import { useEffect } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { X } from 'lucide-react';
import { selectToasts, dismissToast } from '../../store/toastSlice';
import { restoreThread } from '../../store/inboxSlice';
import styles from './Toast.module.css';

function ToastItem({ toast }) {
  const dispatch = useDispatch();

  useEffect(() => {
    const remaining = toast.duration - (Date.now() - toast.createdAt);
    if (remaining <= 0) {
      dispatch(dismissToast(toast.id));
      return;
    }
    const timer = setTimeout(() => {
      dispatch(dismissToast(toast.id));
    }, remaining);
    return () => clearTimeout(timer);
  }, [toast.id, toast.duration, toast.createdAt, dispatch]);

  const handleUndo = () => {
    if (toast.undoKind === 'restoreThread' && toast.undoPayload) {
      dispatch(restoreThread(toast.undoPayload));
    }
    dispatch(dismissToast(toast.id));
  };

  return (
    <div className={styles.toast} role="status">
      <span className={styles.message}>{toast.message}</span>
      {toast.undoKind && (
        <button type="button" className={styles.undoBtn} onClick={handleUndo}>
          Undo
        </button>
      )}
      <button
        type="button"
        className={styles.dismissBtn}
        onClick={() => dispatch(dismissToast(toast.id))}
        aria-label="Dismiss"
      >
        <X size={14} />
      </button>
    </div>
  );
}

export default function ToastContainer() {
  const toasts = useSelector(selectToasts);
  if (!toasts.length) return null;
  return (
    <div className={styles.container}>
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} />
      ))}
    </div>
  );
}
