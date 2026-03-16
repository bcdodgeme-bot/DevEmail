/**
 * Lightweight fetch wrapper that uses httpOnly cookies for auth.
 * Tokens are never stored in JavaScript — the browser sends them automatically
 * via cookies on every same-origin request.
 */

const BASE = '/api';

/** Track whether a refresh is already in progress to avoid duplicates */
let refreshPromise = null;

/**
 * Attempt to refresh the access token using the httpOnly refresh_token cookie.
 * De-duplicates concurrent refresh attempts.
 */
async function refreshAccessToken() {
  if (refreshPromise) return refreshPromise;

  refreshPromise = fetch(`${BASE}/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
    .then(async (res) => {
      if (!res.ok) {
        // Refresh failed — redirect to login
        window.location.href = '/login';
        throw new Error('Session expired');
      }
      return res.json();
    })
    .finally(() => {
      refreshPromise = null;
    });

  return refreshPromise;
}

/**
 * Main fetch wrapper.
 * - Sends cookies automatically (credentials: 'include')
 * - On 401, tries to refresh the token and retry once
 * - Pass { raw: true } to get the raw Response (e.g. for blob downloads)
 */
export async function apiFetch(path, opts = {}) {
  const headers = {
    ...(opts.raw ? {} : { 'Content-Type': 'application/json' }),
    ...opts.headers,
  };

  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers,
    credentials: 'include',
  });

  if (res.status === 401) {
    try {
      await refreshAccessToken();
      // Retry the original request — the new access_token cookie is now set
      const retryRes = await fetch(`${BASE}${path}`, {
        ...opts,
        headers,
        credentials: 'include',
      });

      if (!retryRes.ok) {
        const body = await retryRes.json().catch(() => ({}));
        throw new Error(body.detail || `API error ${retryRes.status}`);
      }
      if (opts.raw) return retryRes;
      return retryRes.json();
    } catch (err) {
      throw err;
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API error ${res.status}`);
  }

  if (opts.raw) return res;
  return res.json();
}
