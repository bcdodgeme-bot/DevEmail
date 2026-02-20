import client from './client';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

export const authAPI = {
  // Local auth — email + password login
  async login(email, password) {
    const { data } = await client.post('/auth/login', { email, password });
    return data;
  },

  // Local auth — register new account
  async register(email, password, displayName = null) {
    const { data } = await client.post('/auth/register', {
      email,
      password,
      display_name: displayName,
    });
    return data;
  },

  // Google OAuth — link a Gmail account (requires auth)
  getGoogleLinkUrl() {
    return `${API_BASE}/auth/google/login`;
  },

  // Get current user info
  async me() {
    const { data } = await client.get('/auth/me');
    return data;
  },

  // Refresh tokens
  async refresh(refreshToken) {
    const { data } = await client.post('/auth/refresh', {
      refresh_token: refreshToken,
    });
    return data;
  },

  // Logout (revoke single refresh token)
  async logout(refreshToken) {
    const { data } = await client.post('/auth/logout', {
      refresh_token: refreshToken,
    });
    return data;
  },

  // Logout all sessions
  async logoutAll() {
    const { data } = await client.post('/auth/logout-all');
    return data;
  },
};
