import { apiFetch } from '../utils/api';

export const authAPI = {
  // Local auth — email + password login
  async login(email, password) {
    return apiFetch('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  },

  // Local auth — register new account
  async register(email, password, displayName = null) {
    return apiFetch('/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        email,
        password,
        display_name: displayName,
      }),
    });
  },

  // Google OAuth — link a Gmail account (requires auth)
  getGoogleLinkUrl() {
    return '/api/auth/google/login';
  },

  // Get current user info
  async me() {
    return apiFetch('/auth/me');
  },

  // Logout (revoke current session — cookie sent automatically)
  async logout() {
    return apiFetch('/auth/logout', {
      method: 'POST',
      body: JSON.stringify({}),
    });
  },

  // Logout all sessions
  async logoutAll() {
    return apiFetch('/auth/logout-all', { method: 'POST' });
  },
};
