import client from './client';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

export const authAPI = {
  // Get the Google OAuth login redirect URL
  getLoginUrl() {
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
