/**
 * Lightweight fetch wrapper that injects the JWT token
 * and automatically refreshes expired tokens.
 */

const BASE = '/api';

/** Track whether a refresh is already in progress to avoid duplicates */
let refreshPromise = null;

function getAccessToken() {
  try {
    return localStorage.getItem('access_token') || null;
  } catch {
    return null;
  }
}

function getRefreshToken() {
  try {
    return localStorage.getItem('refresh_token') || null;
  } catch {
    return null;
  }
}

function storeTokens(accessToken, refreshToken) {
  localStorage.setItem('access_token', accessToken);
  if (refreshToken) {
    localStorage.setItem('refresh_token', refreshToken);
  }
}

function clearAllAuth() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
  window.location.href = '/login';
}

/**
 * Attempt to refresh the access token using the stored refresh token.
 * De-duplicates concurrent refresh attempts.
 */
async function refreshAccessToken() {
  // If a refresh is already in flight, wait for it
  if (refreshPromise) return refreshPromise;

  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    clearAllAuth();
    throw new Error('No refresh token available');
  }

  refreshPromise = fetch(`${BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
    .then(async (res) => {
      if (!res.ok) {
        // Refresh token is also invalid/expired — full logout
        clearAllAuth();
        throw new Error('Refresh token expired');
      }
      const data = await res.json();
      storeTokens(data.access_token, data.refresh_token);
      return data.access_token;
    })
    .finally(() => {
      refreshPromise = null;
    });

  return refreshPromise;
}

/**
 * Main fetch wrapper.
 * - Injects Authorization header
 * - On 401, tries to refresh the token and retry once
 */
export async function apiFetch(path, opts = {}) {
  const token = getAccessToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...opts.headers,
  };

  const res = await fetch(`${BASE}${path}`, { ...opts, headers });

  // If 401, attempt a token refresh and retry the request once
  if (res.status === 401) {
    try {
      const newToken = await refreshAccessToken();
      const retryHeaders = {
        ...headers,
        Authorization: `Bearer ${newToken}`,
      };
      const retryRes = await fetch(`${BASE}${path}`, { ...opts, headers: retryHeaders });

      if (!retryRes.ok) {
        const body = await retryRes.json().catch(() => ({}));
        throw new Error(body.detail || `API error ${retryRes.status}`);
      }
      return retryRes.json();
    } catch (err) {
      // Refresh failed — clearAllAuth already redirects to login
      throw err;
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API error ${res.status}`);
  }

  return res.json();
}
