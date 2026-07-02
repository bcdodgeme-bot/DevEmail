import { useState, useEffect, useCallback, useRef } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import {
  X,
  Minus,
  Maximize2,
  Send,
  Paperclip,
  Sparkles,
} from 'lucide-react';
import { selectAccounts, selectDefaultAccount, fetchAccounts } from '../../store/accountsSlice';
import { archiveThread } from '../../store/inboxSlice';
import { composeAPI, attachmentsAPI } from '../../api/compose';
import { apiFetch } from '../../utils/api';
import { formatBytes } from '../../utils/formatBytes';
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
  // Phase 9 E: open the modal pre-populated with an existing draft.
  // When provided, the modal hydrates body/recipients/subject from it,
  // sets draftId immediately so attachment uploads route through the
  // per-draft endpoint, and fetches any already-attached files.
  editDraft = null,
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
  const [isDrafting, setIsDrafting] = useState(false);
  const [error, setError] = useState(null);

  // Draft tracking for auto-save
  const [draftId, setDraftId] = useState(null);
  const [lastSavedAt, setLastSavedAt] = useState(null);
  const autosaveRef = useRef(null);
  const dirtyRef = useRef(false);

  const bodyRef = useRef(null);

  /* ── Phase 9 attachments ──────────────────────────────────────── */
  // Each item: { uid, id?, file?, filename, content_type, size_bytes,
  //              uploading?, error? }
  // - id present  ⇒ row exists on the server (uploaded or restored)
  // - file present ⇒ local File, not yet uploaded
  // uid is a stable client-side key separate from id (id is null for
  // local files until upload completes).
  const [attachments, setAttachments] = useState([]);
  const [maxBytes, setMaxBytes] = useState(25 * 1024 * 1024);
  const fileInputRef = useRef(null);

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

  /* ── Phase 9 attachment effects + handlers ────────────────────── */

  // Fetch the size cap once on mount.
  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await attachmentsAPI.getLimits();
        if (!cancelled && typeof res?.max_bytes === 'number') {
          setMaxBytes(res.max_bytes);
        }
      } catch {
        // Stay on the conservative 25 MiB default if the call fails.
      }
    })();
    return () => { cancelled = true; };
  }, [isOpen]);

  // Hydrate from a restored draft passed in via the editDraft prop.
  // Sets recipients/subject/body, captures the draft id, and fetches
  // already-attached files. Runs once per editDraft change.
  useEffect(() => {
    if (!isOpen || !editDraft) return;
    setDraftId(editDraft.id);
    setAccountId(editDraft.account_id || '');
    setTo(editDraft.to_addresses || []);
    setCc(editDraft.cc_addresses || []);
    setBcc(editDraft.bcc_addresses || []);
    setSubject(editDraft.subject || '');
    setBodyText(stripHtml(editDraft.body_html || '') || editDraft.body_text || '');
    if (editDraft.cc_addresses?.length || editDraft.bcc_addresses?.length) {
      setShowCcBcc(true);
    }

    let cancelled = false;
    (async () => {
      try {
        const rows = await attachmentsAPI.list(editDraft.id);
        if (cancelled) return;
        setAttachments(rows.map((r) => ({
          uid: `srv-${r.id}`,
          id: r.id,
          filename: r.filename,
          content_type: r.content_type,
          size_bytes: r.size_bytes,
        })));
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load draft attachments');
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, editDraft?.id]);

  const totalAttachmentBytes = attachments.reduce((sum, a) => sum + (a.size_bytes || 0), 0);
  const overCap = totalAttachmentBytes > maxBytes;
  // Soft warning around 18 MiB (matches the encoded-overhead boundary
  // for Gmail-class providers — see Phase 9 spec C.note).
  const SOFT_WARN_BYTES = 18 * 1024 * 1024;
  const showSoftWarn = !overCap && totalAttachmentBytes >= SOFT_WARN_BYTES;

  const handleAttachClick = () => {
    fileInputRef.current?.click();
  };

  // When the user picks files. Append to local state and, if a draftId
  // already exists, push them to the per-draft endpoint immediately.
  const handleFilesChosen = async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = ''; // allow re-picking the same file later
    if (files.length === 0) return;

    const newItems = files.map((f) => ({
      uid: `local-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file: f,
      filename: f.name,
      content_type: f.type || 'application/octet-stream',
      size_bytes: f.size,
    }));
    setAttachments((prev) => [...prev, ...newItems]);

    // If we have a draft, kick off uploads now. Otherwise the files
    // sit locally until Send (multipart /compose path) or until a
    // draft is created via auto-save and the sweep effect catches them.
    if (draftId) {
      await uploadPendingItems(newItems, draftId);
    }
  };

  // Upload a specific list of pending items to a known draftId.
  const uploadPendingItems = async (items, currentDraftId) => {
    if (!items.length) return;
    setAttachments((prev) => prev.map((a) =>
      items.find((i) => i.uid === a.uid) ? { ...a, uploading: true, error: null } : a
    ));
    try {
      const filesPayload = items.map((i) => i.file).filter(Boolean);
      if (!filesPayload.length) return;
      const created = await attachmentsAPI.upload(currentDraftId, filesPayload);
      // Replace the local items with their server-row counterparts. We
      // match on order of upload — the server returns rows in the same
      // order it received them.
      setAttachments((prev) => {
        let createdIdx = 0;
        return prev.map((a) => {
          const isThisBatch = items.find((i) => i.uid === a.uid);
          if (!isThisBatch) return a;
          const row = created[createdIdx++];
          if (!row) return { ...a, uploading: false };
          return {
            uid: `srv-${row.id}`,
            id: row.id,
            filename: row.filename,
            content_type: row.content_type,
            size_bytes: row.size_bytes,
          };
        });
      });
    } catch (err) {
      setAttachments((prev) => prev.map((a) =>
        items.find((i) => i.uid === a.uid)
          ? { ...a, uploading: false, error: err.message || 'Upload failed' }
          : a
      ));
      setError(err.message || 'Failed to upload attachment');
    }
  };

  // When the auto-save creates a draft, sweep up any locally-pending
  // files into the new draft.
  useEffect(() => {
    if (!draftId) return;
    const pending = attachments.filter((a) => a.file && !a.id && !a.uploading);
    if (pending.length === 0) return;
    uploadPendingItems(pending, draftId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftId]);

  const handleRemoveAttachment = async (att) => {
    if (att.id && draftId) {
      // Existing server row — DELETE first, drop locally on success.
      try {
        await attachmentsAPI.delete(draftId, att.id);
      } catch (err) {
        setAttachments((prev) => prev.map((a) =>
          a.uid === att.uid ? { ...a, error: err.message || 'Could not delete' } : a
        ));
        return;
      }
    }
    setAttachments((prev) => prev.filter((a) => a.uid !== att.uid));
  };

  const getCurrentSignature = () => {
    if (!signatureId || !accountId) return '';
    const account = accounts.find((a) => a.id === accountId);
    const sig = account?.signatures?.find((s) => s.id === signatureId);
    return sig?.body_html || sig?.body_text || '';
  };

  /**
   * Preserve pasted hyperlink URLs. A plain <textarea> only captures the
   * *visible text* of a pasted rich link and silently drops the href — which
   * is how a pasted Teams/meeting link disappears from the sent email. When the
   * clipboard carries HTML, pull out any http(s) link whose URL isn't already
   * present in the plain-text version and append it inline, so the URL survives
   * into the body. Plain-text pastes are left untouched (default behavior).
   */
  const handlePaste = (e) => {
    const html = e.clipboardData?.getData('text/html');
    if (!html) return; // plain-text paste already keeps everything

    const plain = e.clipboardData?.getData('text/plain') ?? '';
    let doc;
    try {
      doc = new DOMParser().parseFromString(html, 'text/html');
    } catch {
      return; // malformed HTML — fall back to default paste
    }

    const lostUrls = [];
    doc.querySelectorAll('a[href]').forEach((a) => {
      const href = (a.getAttribute('href') || '').trim();
      if (!/^https?:\/\//i.test(href)) return;                 // only real web links
      if (plain.includes(href) || lostUrls.includes(href)) return; // already visible / dup
      lostUrls.push(href);
    });

    if (!lostUrls.length) return; // no URL would be lost — let the default paste run

    e.preventDefault();
    const insertText = plain
      ? `${plain} ${lostUrls.join(' ')}`
      : lostUrls.join(' ');

    const el = bodyRef.current;
    const start = el?.selectionStart ?? bodyText.length;
    const end = el?.selectionEnd ?? bodyText.length;
    setBodyText(bodyText.slice(0, start) + insertText + bodyText.slice(end));

    // Restore the caret after React re-renders the controlled textarea.
    const caret = start + insertText.length;
    requestAnimationFrame(() => {
      if (bodyRef.current) {
        bodyRef.current.selectionStart = caret;
        bodyRef.current.selectionEnd = caret;
      }
    });
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
    if (overCap) {
      setError(
        `Attachments total ${formatBytes(totalAttachmentBytes)} — ` +
        `over the ${formatBytes(maxBytes)} limit. Remove some files first.`
      );
      return;
    }

    setIsSending(true);
    setError(null);

    try {
      const payload = buildPayload(false);
      const pendingFiles = attachments.filter((a) => a.file && !a.id);

      if (draftId) {
        // Restored-draft / auto-saved-draft path. Sweep any locally-
        // queued files into the draft first, then send by message id.
        if (pendingFiles.length > 0) {
          await uploadPendingItems(pendingFiles, draftId);
        }
        await composeAPI.sendExistingDraft({
          ...payload,
          existing_message_id: draftId,
        });
      } else if (pendingFiles.length > 0) {
        // New compose with attachments — multipart /compose creates the
        // draft + uploads + sends in one request.
        await composeAPI.sendWithAttachments(
          payload,
          pendingFiles.map((p) => p.file),
        );
      } else {
        // No attachments, no draft yet — JSON path (original behavior).
        await composeAPI.send(payload);
      }

      // Auto-archive the thread we replied to
      if (replyTo?.id) {
        dispatch(archiveThread(replyTo.id));
      }
      resetAndClose();
    } catch (err) {
      // 502 from the backend's send-failure path includes "open it
      // from the Drafts folder to retry" — surface as inline error,
      // keep the modal open with attachments intact (Phase 9 E.8).
      setError(err.message || 'Failed to send email');
    } finally {
      setIsSending(false);
    }
  };

  const handleSaveDraft = () => saveDraft(false).then(resetAndClose);

  /** Ask Syntax Prime (via DevEmail proxy) to draft a reply from thread context. */
  const handleDraftWithSyntax = async () => {
    if (!replyTo) return;

    const received = (replyTo.messages || []).find((m) => !m.is_sent && !m.is_draft);
    const sourceMsg = received || (replyTo.messages || [])[0] || replyTo;
    const senderEmail =
      sourceMsg.from_address || replyTo.from_address || replyTo.latest_from_address || '';
    const senderName =
      sourceMsg.from_name || replyTo.from_name || replyTo.latest_from_name || '';

    // messages array is newest-first; take up to 3, convert each to plain text
    const threadMessages = (replyTo.messages || [])
      .slice(0, 3)
      .map((m) => decodeEntities(stripHtml(m.body_html || '') || m.body_text || ''))
      .filter(Boolean);

    if (threadMessages.length === 0) {
      const fallback = decodeEntities(
        stripHtml(replyTo.body_html || '') || replyTo.body_text || replyTo.latest_snippet || ''
      );
      if (fallback) threadMessages.push(fallback);
    }

    setIsDrafting(true);
    setError(null);
    try {
      const res = await apiFetch('/syntax/draft-reply', {
        method: 'POST',
        body: JSON.stringify({
          subject: replyTo.subject || '',
          sender_name: senderName,
          sender_email: senderEmail,
          thread_messages: threadMessages,
        }),
      });
      if (typeof res?.draft === 'string') {
        setBodyText(res.draft);
      } else {
        setError('Syntax returned an empty draft');
      }
    } catch (err) {
      setError(err.message || 'Could not reach Syntax');
    } finally {
      setIsDrafting(false);
    }
  };

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
    setAttachments([]);
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
                onPaste={handlePaste}
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

            {/* Attachments list (Phase 9) */}
            {attachments.length > 0 && (
              <div className={styles.attachments} data-testid="compose-attachments">
                <div className={styles.attachmentList}>
                  {attachments.map((att) => (
                    <div
                      key={att.uid}
                      className={[
                        styles.attachmentItem,
                        att.uploading ? styles.attachmentUploading : '',
                        att.error ? styles.attachmentError : '',
                      ].filter(Boolean).join(' ')}
                    >
                      <Paperclip size={12} className={styles.attachmentIcon} />
                      {att.id && draftId ? (
                        <a
                          href={attachmentsAPI.downloadUrl(draftId, att.id)}
                          className={styles.attachmentName}
                          download={att.filename}
                        >
                          {att.filename}
                        </a>
                      ) : (
                        <span className={styles.attachmentName}>{att.filename}</span>
                      )}
                      <span className={styles.attachmentSize}>
                        {formatBytes(att.size_bytes)}
                      </span>
                      {att.uploading && (
                        <span className={styles.attachmentStatus}>uploading…</span>
                      )}
                      {att.error && (
                        <span className={styles.attachmentStatus} title={att.error}>
                          {att.error}
                        </span>
                      )}
                      <button
                        type="button"
                        className={styles.attachmentRemove}
                        onClick={() => handleRemoveAttachment(att)}
                        title="Remove attachment"
                        aria-label={`Remove ${att.filename}`}
                      >
                        <X size={12} />
                      </button>
                    </div>
                  ))}
                </div>
                <div
                  className={[
                    styles.attachmentMeter,
                    overCap ? styles.attachmentMeterOver : '',
                    showSoftWarn ? styles.attachmentMeterWarn : '',
                  ].filter(Boolean).join(' ')}
                  data-testid="compose-attachments-meter"
                >
                  {formatBytes(totalAttachmentBytes)} / {formatBytes(maxBytes)} used
                  {overCap && (
                    <span className={styles.attachmentMeterMsg}>
                      — over the limit, remove some files to send
                    </span>
                  )}
                  {showSoftWarn && (
                    <span className={styles.attachmentMeterMsg}>
                      — approaching Gmail's practical limit (encoding overhead)
                    </span>
                  )}
                </div>
              </div>
            )}

            {error && <div className={styles.error}>{error}</div>}

            <div className={styles.footer}>
              <button
                className={styles.sendButton}
                onClick={handleSend}
                disabled={isSending || to.length === 0 || overCap}
                type="button"
              >
                <Send size={14} />
                <span>{isSending ? 'Sending...' : 'Send'}</span>
              </button>

              <div className={styles.footerRight}>
                {replyTo && (
                  <button
                    className={styles.footerBtn}
                    onClick={handleDraftWithSyntax}
                    disabled={isDrafting}
                    title="Draft this reply with Syntax"
                    type="button"
                  >
                    <Sparkles size={14} />
                    <span>{isDrafting ? 'Drafting…' : 'Draft with Syntax'}</span>
                  </button>
                )}
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
                  onClick={handleAttachClick}
                  data-testid="compose-attach-button"
                >
                  <Paperclip size={16} />
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  hidden
                  data-testid="compose-file-input"
                  onChange={handleFilesChosen}
                />
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
