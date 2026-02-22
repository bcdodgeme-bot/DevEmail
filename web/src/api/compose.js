import { apiFetch } from '../utils/api';

export const composeAPI = {
  /**
   * Send an email or save as draft.
   * Matches backend ComposeRequest schema.
   */
  async send(data) {
    return apiFetch('/messages/compose', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * Update an existing draft.
   * Matches backend DraftUpdateRequest schema.
   */
  async updateDraft(messageId, data) {
    return apiFetch(`/messages/${messageId}/draft`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  /**
   * Search contacts for autocomplete.
   * Returns { contacts, total, page, per_page }
   */
  async searchContacts(query, limit = 8) {
    const params = new URLSearchParams({
      search: query,
      per_page: limit,
    });
    return apiFetch(`/contacts?${params}`);
  },
};
