import { useState } from 'react';
import { ChevronDown, ChevronUp, Paperclip, Download } from 'lucide-react';
import DOMPurify from 'dompurify';
import { getAvatarGradient } from '../../utils/avatarColor';
import { formatRelativeDate } from '../../utils/formatDate';
import { formatBytes } from '../../utils/formatBytes';
import { apiFetch } from '../../utils/api';
import styles from './MessageBubble.module.css';

function getInitials(name, address) {
  if (name) {
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    return name[0].toUpperCase();
  }
  if (address) return address[0].toUpperCase();
  return '?';
}

function formatAddressList(addresses) {
  if (!addresses || !addresses.length) return '';
  return addresses
    .map((a) => (typeof a === 'string' ? a : a.name || a.address || a.email))
    .join(', ');
}

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

export default function MessageBubble({ message }) {
  const [expanded, setExpanded] = useState(true);
  const [downloading, setDownloading] = useState(null);

  const initials = getInitials(message.from_name, message.from_address);
  const gradient = getAvatarGradient(message.from_name || message.from_address || '');
  const displayName = message.from_name || message.from_address || 'Unknown';
  const dateStr = formatRelativeDate(message.received_at || message.sent_at || message.created_at);
  const toStr = formatAddressList(message.to_addresses);
  const ccStr = formatAddressList(message.cc_addresses);

  const handleAttachmentDownload = async (attachment) => {
    setDownloading(attachment.id);
    try {
      const response = await apiFetch(
        `/messages/${message.id}/attachments/${attachment.id}/download`,
        { raw: true }
      );
      // If apiFetch returns raw response, create a blob download
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = attachment.filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Attachment download failed:', err);
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className={`${styles.bubble} ${message.is_draft ? styles.draft : ''}`}>
      {/* Header row */}
      <div className={styles.header} onClick={() => setExpanded(!expanded)}>
        <div className={styles.avatar} style={{ background: gradient }}>
          {initials}
        </div>
        <div className={styles.meta}>
          <div className={styles.topLine}>
            <span className={styles.sender}>{displayName}</span>
            {message.is_draft && <span className={styles.draftBadge}>Draft</span>}
            <span className={styles.date}>{dateStr}</span>
          </div>
          <div className={styles.recipients}>
            {toStr && <span>To: {toStr}</span>}
            {ccStr && <span className={styles.cc}> · Cc: {ccStr}</span>}
          </div>
        </div>
        <button className={styles.expandBtn}>
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>

      {/* Body */}
      {expanded && (
        <div className={styles.body}>
          {message.body_html ? (
            <div
              className={styles.htmlContent}
              dangerouslySetInnerHTML={{ __html: sanitizeHtml(message.body_html) }}
            />
          ) : (
            <pre className={styles.textContent}>{message.body_text || message.snippet || ''}</pre>
          )}

          {/* Attachments */}
          {message.attachments?.length > 0 && (
            <div className={styles.attachments}>
              {message.attachments.map((att) => (
                <button
                  key={att.id}
                  className={styles.attachment}
                  onClick={() => handleAttachmentDownload(att)}
                  disabled={downloading === att.id}
                  type="button"
                  title={`Download ${att.filename}`}
                >
                  <Paperclip size={14} />
                  <span className={styles.attName}>{att.filename}</span>
                  <span className={styles.attSize}>{formatBytes(att.size_bytes)}</span>
                  <Download size={12} className={styles.attDownload} />
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
