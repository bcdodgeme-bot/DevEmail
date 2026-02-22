import { apiFetch } from '../utils/api';

export const contactsAPI = {
  /** List contacts with search, pagination, tag filtering */
  async list({ search, page = 1, perPage = 50, tag, favoritesOnly } = {}) {
    const params = new URLSearchParams({ page, per_page: perPage });
    if (search) params.set('search', search);
    if (tag) params.set('tag', tag);
    if (favoritesOnly) params.set('is_favorite', 'true');
    return apiFetch(`/contacts?${params}`);
  },

  /** Get full contact detail */
  async get(contactId) {
    return apiFetch(`/contacts/${contactId}`);
  },

  /** Create a new contact */
  async create(data) {
    return apiFetch('/contacts', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /** Update a contact */
  async update(contactId, data) {
    return apiFetch(`/contacts/${contactId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  /** Delete a contact */
  async remove(contactId) {
    return apiFetch(`/contacts/${contactId}`, { method: 'DELETE' });
  },

  /** Toggle favorite */
  async toggleFavorite(contactId) {
    return apiFetch(`/contacts/${contactId}/favorite`, { method: 'PATCH' });
  },
};
