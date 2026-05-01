import { apiFetch } from '../utils/api';

/**
 * Multipart helper. Goes around apiFetch so we can keep cookies/refresh
 * behavior consistent without forcing apiFetch to know about FormData.
 *
 * Note: do NOT set Content-Type — the browser sets it (with the
 * boundary) when fetch sees a FormData body.
 */
async function fetchMultipart(path, formData, { method = 'POST' } = {}) {
  const res = await fetch(`/api${path}`, {
    method,
    body: formData,
    credentials: 'include',
  });
  if (!res.ok) {
    let detail;
    try { detail = (await res.json()).detail; } catch { /* ignore */ }
    throw new Error(detail || `API error ${res.status}`);
  }
  return res.json();
}

export const composeAPI = {
  /**
   * Send an email or save as draft (JSON body, no attachments).
   * Matches backend ComposeRequest schema.
   */
  async send(data) {
    return apiFetch('/messages/compose', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * Send a brand-new compose with one or more attachments. Goes via
   * multipart/form-data to /compose. Backend creates the draft +
   * attachment rows + sends, all in one call.
   *
   * `payload` is the same shape as `send()`; `files` is an array of File.
   */
  async sendWithAttachments(payload, files) {
    const fd = new FormData();
    fd.append('payload', JSON.stringify(payload));
    for (const f of files) {
      fd.append('attachments', f, f.name);
    }
    return fetchMultipart('/messages/compose', fd);
  },

  /**
   * Send a previously-built draft. Backend treats the draft as the
   * Message to send (no new row), reuses already-attached files. Use
   * `uploadAttachmentsToDraft` first to push any newly-added files.
   */
  async sendExistingDraft(payload) {
    return apiFetch('/messages/compose', {
      method: 'POST',
      body: JSON.stringify({ ...payload, is_draft: false }),
    });
  },

  /** Update an existing draft (body / recipients only — no attachments here). */
  async updateDraft(messageId, data) {
    return apiFetch(`/messages/${messageId}/draft`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  /** Search contacts for autocomplete. */
  async searchContacts(query, limit = 8) {
    const params = new URLSearchParams({ search: query, per_page: limit });
    return apiFetch(`/contacts?${params}`);
  },
};

/* ── Attachment endpoints (Phase 9) ─────────────────────────────── */

export const attachmentsAPI = {
  /** Server-authoritative size cap. Frontend uses for UX gating only. */
  async getLimits() {
    return apiFetch('/messages/config/attachments');
  },

  /** List attachments on a message (metadata only). */
  async list(messageId) {
    return apiFetch(`/messages/${messageId}/attachments`);
  },

  /**
   * Upload one or more files to an existing draft. Multipart only.
   * Returns the newly-created attachment metadata rows.
   */
  async upload(messageId, files) {
    const fd = new FormData();
    for (const f of files) {
      fd.append('attachments', f, f.name);
    }
    return fetchMultipart(`/messages/${messageId}/attachments`, fd);
  },

  /** Remove an attachment row + its on-disk file. 204 on success. */
  async delete(messageId, attachmentId) {
    return apiFetch(
      `/messages/${messageId}/attachments/${attachmentId}`,
      { method: 'DELETE', raw: true },
    );
  },

  /** Build the URL the modal can hand to <a href> for download. */
  downloadUrl(messageId, attachmentId) {
    return `/api/messages/${messageId}/attachments/${attachmentId}/download`;
  },
};
