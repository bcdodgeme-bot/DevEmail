import { useState, useEffect, useCallback, useRef } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import {
  X,
  Minus,
  Maximize2,
  Send,
  Paperclip,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { selectAccounts, selectDefaultAccount, fetchAccounts } from '../../store/accountsSlice';
import { composeAPI } from '../../api/compose';
import AccountPicker from './AccountPicker';
import RecipientInput from './RecipientInput';
import styles from './ComposeModal.module.css';

/**
 * ComposeModal — full email compose experience.
 *
 * Props:
 *   isOpen        - boolean
 *   onClose       - () => void
 *   replyTo       - optional MessageDetailResponse to pre-fill reply
 *   replyAll      - boolean, if true pre-fill all recipients
 *   forward       - optional MessageDetailResponse to pre-fill forward
 */
export default function ComposeModal({
  isOpen,
  onClose,
  replyTo = null,
  replyAll = false,
  forward = null,
}) {
  const dispatch = useDispatch();
  const accounts = useSelector(selectAccounts);
  const defaultAccount = useSelector(selectDefaultAccount);

  /* Form state */
  const [accountId, setAccountId] = useState('');
  const [signatureId, setSignatureId] = useState('');
  const [to, setTo] = useState([]);
  const [cc, setCc] = useState([]);
  const [bcc, setBcc] = useState([]);
  const [subject, setSubject] = useState('');
  const [bodyHtml, setBodyHtml] = useState('');
  const [showCcBcc, setShowCcBcc] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState(null);

  const bodyRef = useRef(null);

  /* Fetch accounts if not loaded */
  useEffect(() => {
    if (accounts.length === 0) {
      dispatch(fetchAccounts());
    }
  }, [accounts.length, dispatch]);

  /* Set default account when loaded */
  useEffect(() => {
    if (defaultAccount && !accountId) {
      setAccountId(defaultAccount.id);
      const defaultSig = defaultAccount.signatures?.find((s) => s.is_default);
      if (defaultSig) setSignatureId(defaultSig.id);
    }
  }, [defaultAccount, accountId]);

  /* Pre-fill for reply/forward */
  useEffect(() => {
    if (!isOpen) return;

    if (replyTo) {
      setTo([{ address: replyTo.from_address, name: replyTo.from_name }]);
      setSubject(
        replyTo.subject?.startsWith('Re:')
          ? replyTo.subject
          : `Re: ${replyTo.subject || ''}`
      );
      if (replyAll) {
        const allRecipients = [
          ...(replyTo.to_addresses || []),
          ...(replyTo.cc_addresses || []),
        ].filter((r) => r.address !== replyTo.from_address);
        setCc(allRecipients);
        setShowCcBcc(allRecipients.length > 0);
      }
      setBodyHtml(
        `<br/><br/><div style="border-left:2px solid #64748b;padding-left:12px;color:#64748b;">` +
        `<p>On ${new Date(replyTo.received_at || replyTo.sent_at).toLocaleString()}, ` +
        `${replyTo.from_name || replyTo.from_address} wrote:</p>` +
        `${replyTo.body_html || replyTo.body_text || ''}</div>`
      );
    } else if (forward) {
      setSubject(
        forward.subject?.startsWith('Fwd:')
          ? forward.subject
          : `Fwd: ${forward.subject || ''}`
      );
      setBodyHtml(
        `<br/><br/>---------- Forwarded message ----------<br/>` +
        `From: ${forward.from_name || ''} &lt;${forward.from_address || ''}&gt;<br/>` +
        `Subject: ${forward.subject || ''}<br/>` +
        `Date: ${new Date(forward.received_at || forward.sent_at).toLocaleString()}<br/><br/>` +
        `${forward.body_html || forward.body_text || ''}`
      );
    }
  }, [isOpen, replyTo, replyAll, forward]);

  /* Handle account switch — update signature */
  const handleAccountChange = useCallback(
    (newAccountId) => {
      setAccountId(newAccountId);
      const account = accounts.find((a) => a.id === newAccountId);
      const defaultSig = account?.signatures?.find((s) => s.is_default);
      setSignatureId(defaultSig?.id || '');
    },
    [accounts]
  );

  /* Get current signature HTML */
  const getCurrentSignature = () => {
    if (!signatureId || !accountId) return '';
    const account = accounts.find((a) => a.id === accountId);
    const sig = account?.signatures?.find((s) => s.id === signatureId);
    return sig?.body_html || sig?.body_text || '';
  };

  /* Send email */
  const handleSend = async () => {
    if (to.length === 0) {
      setError('Please add at least one recipient');
      return;
    }
    if (!accountId) {
      setError('Please select an account to send from');
      return;
    }

    setIsSending(true);
    setError(null);

    try {
      await composeAPI.send({
        account_id: accountId,
        to_addresses: to,
        cc_addresses: cc,
        bcc_addresses: bcc,
        subject,
        body_html: bodyHtml,
        signature_id: signatureId || undefined,
        is_draft: false,
      });
      resetAndClose();
    } catch (err) {
      setError(err.message || 'Failed to send email');
    } finally {
      setIsSending(false);
    }
  };

  /* Save as draft */
  const handleSaveDraft = async () => {
    if (!accountId) return;
    setError(null);

    try {
      await composeAPI.send({
        account_id: accountId,
        to_addresses: to,
        cc_addresses: cc,
        bcc_addresses: bcc,
        subject,
        body_html: bodyHtml,
        signature_id: signatureId || undefined,
        is_draft: true,
      });
      resetAndClose();
    } catch (err) {
      setError(err.message || 'Failed to save draft');
    }
  };

  /* Reset form and close */
  const resetAndClose = () => {
    setTo([]);
    setCc([]);
    setBcc([]);
    setSubject('');
    setBodyHtml('');
    setShowCcBcc(false);
    setIsMinimized(false);
    setIsMaximized(false);
    setError(null);
    setAccountId(defaultAccount?.id || '');
    onClose();
  };

  /* Keyboard shortcut: Cmd+Enter to send */
  useEffect(() => {
    if (!isOpen) return;
    function handleKey(e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        handleSend();
      }
      if (e.key === 'Escape') {
        if (to.length || subject || bodyHtml) {
          handleSaveDraft();
        } else {
          resetAndClose();
        }
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [isOpen, to, subject, bodyHtml, accountId]);

  if (!isOpen) return null;

  const selectedAccount = accounts.find((a) => a.id === accountId);
  const signatures = selectedAccount?.signatures || [];

  return (
    <div
      className={`${styles.overlay} ${isMaximized ? styles.overlayMax : ''}`}
      onClick={(e) => {
        if (e.target === e.currentTarget) handleSaveDraft();
      }}
    >
      <div
        className={`${styles.modal} ${
          isMinimized ? styles.minimized : ''
        } ${isMaximized ? styles.maximized : ''}`}
      >
        {/* Header */}
        <div className={styles.header}>
          <span className={styles.headerTitle}>
            {replyTo ? 'Reply' : forward ? 'Forward' : 'New Message'}
          </span>
          <div className={styles.headerActions}>
            <button
              className={styles.headerBtn}
              onClick={() => setIsMinimized(!isMinimized)}
              title={isMinimized ? 'Expand' : 'Minimize'}
              type="button"
            >
              <Minus size={14} />
            </button>
            <button
              className={styles.headerBtn}
              onClick={() => setIsMaximized(!isMaximized)}
              title={isMaximized ? 'Restore' : 'Maximize'}
              type="button"
            >
              <Maximize2 size={14} />
            </button>
            <button
              className={styles.headerBtn}
              onClick={resetAndClose}
              title="Discard"
              type="button"
            >
              <X size={14} />
            </button>
          </div>
        </div>

        {!isMinimized && (
          <>
            {/* Account Picker — "Send From" */}
            <div className={styles.row}>
              <AccountPicker
                accounts={accounts}
                selectedId={accountId}
                onChange={handleAccountChange}
              />
            </div>

            {/* Recipients */}
            <div className={styles.row}>
              <RecipientInput
                label="To"
                value={to}
                onChange={setTo}
                placeholder="Recipients"
              />
              {!showCcBcc && (
                <button
                  className={styles.ccToggle}
                  onClick={() => setShowCcBcc(true)}
                  type="button"
                >
                  Cc/Bcc
                </button>
              )}
            </div>

            {showCcBcc && (
              <>
                <div className={styles.row}>
                  <RecipientInput
                    label="Cc"
                    value={cc}
                    onChange={setCc}
                    placeholder="Carbon copy"
                  />
                </div>
                <div className={styles.row}>
                  <RecipientInput
                    label="Bcc"
                    value={bcc}
                    onChange={setBcc}
                    placeholder="Blind carbon copy"
                  />
                </div>
              </>
            )}

            {/* Subject */}
            <div className={styles.row}>
              <span className={styles.fieldLabel}>Subj</span>
              <input
                className={styles.subjectInput}
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="Subject"
              />
            </div>

            {/* Body */}
            <div className={styles.body}>
              <textarea
                ref={bodyRef}
                className={styles.bodyInput}
                value={bodyHtml}
                onChange={(e) => setBodyHtml(e.target.value)}
                placeholder="Write your message..."
              />
            </div>

            {/* Signature preview */}
            {signatures.length > 0 && (
              <div className={styles.signatureBar}>
                <label className={styles.sigLabel}>
                  Signature:
                  <select
                    className={styles.sigSelect}
                    value={signatureId}
                    onChange={(e) => setSignatureId(e.target.value)}
                  >
                    <option value="">None</option>
                    {signatures.map((sig) => (
                      <option key={sig.id} value={sig.id}>
                        {sig.name} {sig.is_default ? '(default)' : ''}
                      </option>
                    ))}
                  </select>
                </label>
                {signatureId && (
                  <div
                    className={styles.sigPreview}
                    dangerouslySetInnerHTML={{ __html: getCurrentSignature() }}
                  />
                )}
              </div>
            )}

            {/* Error */}
            {error && <div className={styles.error}>{error}</div>}

            {/* Footer */}
            <div className={styles.footer}>
              <button
                className={styles.sendButton}
                onClick={handleSend}
                disabled={isSending || to.length === 0}
                type="button"
              >
                <Send size={14} />
                <span>{isSending ? 'Sending...' : 'Send'}</span>
              </button>

              <div className={styles.footerRight}>
                <button
                  className={styles.footerBtn}
                  onClick={handleSaveDraft}
                  title="Save as draft"
                  type="button"
                >
                  Save Draft
                </button>
                <button
                  className={styles.footerBtn}
                  title="Attach file"
                  type="button"
                >
                  <Paperclip size={16} />
                </button>
                <button
                  className={`${styles.footerBtn} ${styles.discardBtn}`}
                  onClick={resetAndClose}
                  title="Discard"
                  type="button"
                >
                  <X size={16} />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
