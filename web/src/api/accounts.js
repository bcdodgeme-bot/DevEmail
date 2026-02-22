import { apiFetch } from '../utils/api';

export const accountsAPI = {
  /** List all linked email accounts */
  async list() {
    return apiFetch('/accounts');
  },

  /** Get single account details */
  async get(accountId) {
    return apiFetch(`/accounts/${accountId}`);
  },

  /** Link a Stalwart mail server account */
  async linkStalwart(data) {
    return apiFetch('/accounts/stalwart', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /** Update account settings */
  async update(accountId, data) {
    return apiFetch(`/accounts/${accountId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  /** Unlink an account */
  async remove(accountId) {
    return apiFetch(`/accounts/${accountId}`, { method: 'DELETE' });
  },

  /** List signatures for an account */
  async getSignatures(accountId) {
    return apiFetch(`/accounts/${accountId}/signatures`);
  },

  /** Create a signature */
  async createSignature(accountId, data) {
    return apiFetch(`/accounts/${accountId}/signatures`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /** Update a signature */
  async updateSignature(accountId, signatureId, data) {
    return apiFetch(`/accounts/${accountId}/signatures/${signatureId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  /** Delete a signature */
  async deleteSignature(accountId, signatureId) {
    return apiFetch(`/accounts/${accountId}/signatures/${signatureId}`, {
      method: 'DELETE',
    });
  },

  /** Get the Google OAuth link URL */
  getGoogleLinkUrl() {
    return '/api/auth/google/login';
  },
};
