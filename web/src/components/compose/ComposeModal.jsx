import { useState, useEffect, useCallback, useRef } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import {
  X,
  Minus,
  Maximize2,
  Send,
  Paperclip,
} from 'lucide-react';
import { selectAccounts, selectDefaultAccount, fetchAccounts } from '../../store/accountsSlice';
import { archiveThread } from '../../store/inboxSlice';
import { composeAPI } from '../../api/compose';
import { apiFetch } from '../../utils/api';
import AccountPicker from './AccountPicker';
import RecipientInput from './RecipientInput';
import styles from './ComposeModal.module.css';

const AUTOSAVE_INTERVAL = 30000; // 30 seconds

/** Decode HTML entities like &#39; &amp; &lt; into their literal characters. */
function decodeEntities(text) {
  if (!text) return '';
  const ta = document.createElement('textarea');
  ta.innerHTML = text;
  return ta.value;
}

function stripHtml(html) {
  if (!html) return '';
  const doc = new DOMParser().parseFromString(html, 'text/html');
  return doc.body.textContent || '';
}

/**
 * Convert plain text to simple HTML.
 * Splits on double newlines into <p> blocks, single newlines become <br>.
 */
function textToHtml(text) {
  if (!text || !text.trim()) return '';
  // Split on double newlines to create paragraphs
  const paragraphs = text.split(/\n{2,}/);
  return paragraphs
    .map((p) => {
      const escaped = p
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\n/g, '<br>');
      return `<p>${escaped}</p>`;
    })
    .join('');
}

export default function ComposeModal({
  isOpen,
  onClose,
  replyTo = null,
  replyAll = false,
  forward = null,
  prefillTo = null,
}) {
  const dispatch = useDispatch();
  const accounts = useSelector(selectAccounts);
  const defaultAccount = useSelector(selectDefaultAccount);

  const [accountId, setAccountId] = useState('');
  const [signatureId, setSignatureId] = useState('');
  const [to, setTo] = useState([]);
  const [cc, setCc] = useState([]);
  const [bcc, setBcc] = useState([]);
  const [subject, setSubject] = useState('');
  const [bodyText, setBodyText] = useState('');
  const [showCcBcc, setShowCcBcc] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState(null);

  // Draft tracking for auto-save
  const [draftId, setDraftId] = useState(null);
  const [lastSavedAt, setLastSavedAt] = useState(null);
  const autosaveRef = useRef(null);
  const dirtyRef = useRef(false);

  const bodyRef = useRef(null);

  useEffect(() => {
    if (accounts.length === 0) {
      dispatch(fetchAccounts());
    }
  }, [accounts.length, dispatch]);

  useEffect(() => {
    if (defaultAccount && !accountId) {
      setAccountId(defaultAccount.id);
      const defaultSig = defaultAccount.signatures?.find((s) => s.is_default);
      if (defaultSig) setSignatureId(defaultSig.id);
    }
  }, [defaultAccount, accountId]);

  useEffect(() => {
    if (!isOpen) return;

    if (replyTo) {
      // Find the latest received message in the thread — its account_id is the
      // inbox that received the email. Thread detail messages are newest-first.
      const received = (replyTo.messages || []).find((m) => !m.is_sent && !m.is_draft);
      const sourceMsg = received || (replyTo.messages || [])[0] || replyTo;

      const fromAddr = sourceMsg.from_address || replyTo.from_address || replyTo.latest_from_address || '';
      const fromName = sourceMsg.from_name || replyTo.from_name || replyTo.latest_from_name || '';

      // Auto-select the account that received this email, and its default signature
      const receivingAccountId = sourceMsg.account_id;
      if (receivingAccountId) {
        setAccountId(receivingAccountId);
        const receivingAccount = accounts.find((a) => a.id === receivingAccountId);
        const defaultSig = receivingAccount?.signatures?.find((s) => s.is_default);
        setSignatureId(defaultSig?.id || '');
      }

      setTo([{ address: fromAddr, name: fromName }]);
      setSubject(
        replyTo.subject?.startsWith('Re:')
          ? replyTo.subject
          : `Re: ${replyTo.subject || ''}`
      );
      if (replyAll) {
        const allRecipients = [
          ...(sourceMsg.to_addresses || replyTo.to_addresses || []),
          ...(sourceMsg.cc_addresses || replyTo.cc_addresses || []),
        ].filter((r) => r.address !== fromAddr);
        setCc(allRecipients);
        setShowCcBcc(allRecipients.length > 0);
      }

      const replyDate = sourceMsg.received_at || sourceMsg.sent_at || replyTo.last_message_at;
      const replyName = fromName || fromAddr || '';
      const dateStr = replyDate ? new Date(replyDate).toLocaleString() : '';
      const rawOriginal =
        stripHtml(sourceMsg.body_html || replyTo.body_html || '') ||
        sourceMsg.body_text ||
        replyTo.body_text ||
        replyTo.latest_snippet ||
        '';
      const originalText = decodeEntities(rawOriginal);

      // Look up contact for greeting
      (async () => {
        let greeting = '';
        if (fromAddr) {
          try {
            const res = await apiFetch(`/contacts?search=${encodeURIComponent(fromAddr)}&per_page=5`);
            const match = (res.contacts || []).find((c) => {
              const emails = c.emails || [];
              return emails.some((e) => {
                const addr = typeof e === 'string' ? e : e.address || e.email;
                return addr && addr.toLowerCase() === fromAddr.toLowerCase();
              });
            });
            if (match?.first_name) {
              greeting = `Hello ${match.first_name},\n\n`;
            }
          } catch {
            // Ignore contact lookup failures
          }
        }
        setBodyText(
          `${greeting}\n\nOn ${dateStr}, ${replyName} wrote:\n> ${originalText.replace(/\n/g, '\n> ')}`
        );
      })();
    } else if (forward) {
      setSubject(
        forward.subject?.startsWith('Fwd:')
          ? forward.subject
          : `Fwd: ${forward.subject || ''}`
      );
      const fwdDate = forward.received_at || forward.sent_at || forward.last_message_at;
      const fwdName = forward.from_name || forward.latest_from_name || '';
      const fwdAddr = forward.from_address || forward.latest_from_address || '';
      const fwdDateStr = fwdDate ? new Date(fwdDate).toLocaleString() : '';
      const fwdText = decodeEntities(
        stripHtml(forward.body_html || '') || forward.body_text || forward.latest_snippet || ''
      );
      setBodyText(
        `\n\n---------- Forwarded message ----------\n` +
        `From: ${fwdName} <${fwdAddr}>\n` +
        `Subject: ${forward.subject || ''}\n` +
        `Date: ${fwdDateStr}\n\n` +
        fwdText
      );
    } else if (prefillTo) {
      // Compose from contacts — prefill the To field
      const recipients = Array.isArray(prefillTo) ? prefillTo : [prefillTo];
      setTo(
        recipients.map((r) =>
          typeof r === 'string' ? { address: r, name: '' } : r
        )
      );
    }
    // Intentionally omit `accounts` from deps so that fetchAccounts mid-compose
    // doesn't reset the form. Signature resolution falls back to a separate effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, replyTo, replyAll, forward, prefillTo]);

  // When accounts load after reply init, resolve the default signature for the chosen account
  useEffect(() => {
    if (!accountId || signatureId) return;
    const account = accounts.find((a) => a.id === accountId);
    const defaultSig = account?.signatures?.find((s) => s.is_default);
    if (defaultSig) setSignatureId(defaultSig.id);
  }, [accounts, accountId, signatureId]);

  // Mark dirty on any field change
  useEffect(() => {
    dirtyRef.current = true;
  }, [to, cc, bcc, subject, bodyText]);

  // Auto-save interval
  useEffect(() => {
    if (!isOpen) return;

    autosaveRef.current = setInterval(() => {
      if (dirtyRef.current && accountId) {
        saveDraft(true);
      }
    }, AUTOSAVE_INTERVAL);

    return () => clearInterval(autosaveRef.current);
  }, [isOpen, accountId, draftId]);

  const handleAccountChange = useCallback(
    (newAccountId) => {
      setAccountId(newAccountId);
      const account = accounts.find((a) => a.id === newAccountId);
      const defaultSig = account?.signatures?.find((s) => s.is_default);
      setSignatureId(defaultSig?.id || '');
    },
    [accounts]
  );

  const getCurrentSignature = () => {
    if (!signatureId || !accountId) return '';
    const account = accounts.find((a) => a.id === accountId);
    const sig = account?.signatures?.find((s) => s.id === signatureId);
    return sig?.body_html || sig?.body_text || '';
  };

  /** Build the draft/send payload */
  const buildPayload = (isDraft) => ({
    account_id: accountId,
    to_addresses: to,
    cc_addresses: cc,
    bcc_addresses: bcc,
    subject,
    body_html: textToHtml(bodyText),
    body_text: bodyText,
    signature_id: signatureId || undefined,
    is_draft: isDraft,
  });

  /** Save draft — silent when auto=true */
  const saveDraft = async (auto = false) => {
    if (!accountId) return;
    // Don't auto-save empty drafts
    if (auto && !to.length && !subject && !bodyText) return;

    try {
      if (draftId) {
        // Update existing draft
        await composeAPI.updateDraft(draftId, buildPayload(true));
      } else {
        // Create new draft
        const result = await composeAPI.send(buildPayload(true));
        if (result.message_id) {
          setDraftId(result.message_id);
        }
      }
      dirtyRef.current = false;
      setLastSavedAt(new Date());
      if (!auto) setError(null);
    } catch (err) {
      if (!auto) setError(err.message || 'Failed to save draft');
    }
  };

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
      await composeAPI.send(buildPayload(false));
      // Auto-archive the thread we replied to
      if (replyTo?.id) {
        dispatch(archiveThread(replyTo.id));
      }
      resetAndClose();
    } catch (err) {
      setError(err.message || 'Failed to send email');
    } finally {
      setIsSending(false);
    }
  };

  const handleSaveDraft = () => saveDraft(false).then(resetAndClose);

  const resetAndClose = () => {
    clearInterval(autosaveRef.current);
    setTo([]);
    setCc([]);
    setBcc([]);
    setSubject('');
    setBodyText('');
    setShowCcBcc(false);
    setIsMinimized(false);
    setIsMaximized(false);
    setError(null);
    setDraftId(null);
    setLastSavedAt(null);
    dirtyRef.current = false;
    setAccountId(defaultAccount?.id || '');
    onClose();
  };

  /** Save draft on body blur */
  const handleBodyBlur = () => {
    if (dirtyRef.current && accountId && (to.length || subject || bodyText)) {
      saveDraft(true);
    }
  };

  useEffect(() => {
    if (!isOpen) return;
    function handleKey(e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        handleSend();
      }
      if (e.key === 'Escape') {
        if (to.length || subject || bodyText) {
          saveDraft(false).then(resetAndClose);
        } else {
          resetAndClose();
        }
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [isOpen, to, subject, bodyText, accountId]);

  if (!isOpen) return null;

  const selectedAccount = accounts.find((a) => a.id === accountId);
  const signatures = selectedAccount?.signatures || [];

  return (
    <div
      className={`${styles.overlay} ${isMaximized ? styles.overlayMax : ''}`}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          saveDraft(false).then(resetAndClose);
        }
      }}
    >
      <div
        className={`${styles.modal} ${
          isMinimized ? styles.minimized : ''
        } ${isMaximized ? styles.maximized : ''}`}
      >
        <div className={styles.header}>
          <span className={styles.headerTitle}>
            {replyTo ? 'Reply' : forward ? 'Forward' : 'New Message'}
            {lastSavedAt && (
              <span className={styles.savedHint}>
                {' '}· Draft saved
              </span>
            )}
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
            <div className={styles.row}>
              <AccountPicker
                accounts={accounts}
                selectedId={accountId}
                onChange={handleAccountChange}
              />
            </div>

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

            <div className={styles.body}>
              <textarea
                ref={bodyRef}
                className={styles.bodyInput}
                value={bodyText}
                onChange={(e) => setBodyText(e.target.value)}
                onBlur={handleBodyBlur}
                placeholder="Write your message..."
              />
            </div>

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

            {error && <div className={styles.error}>{error}</div>}

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
                  onClick={() => saveDraft(false).then(resetAndClose)}
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
