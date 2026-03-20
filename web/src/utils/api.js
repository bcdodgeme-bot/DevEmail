/**
 * Lightweight fetch wrapper that uses httpOnly cookies for auth.
 * Tokens are never stored in JavaScript — the browser sends them automatically
 * via cookies on every same-origin request.
 */

const BASE = '/api';

/** Circuit breaker state for token refresh */
let refreshPromise = null;
let refreshFailures = 0;
const MAX_REFRESH_FAILURES = 3;
const BACKOFF_BASE_MS = 500;

/**
 * Redirect to login and stop the refresh cycle.
 * The ?session_expired=1 param signals initializeAuth to skip the API call.
 */
function redirectToLogin() {
  refreshFailures = 0;
  refreshPromise = null;
  window.location.href = '/login?session_expired=1';
}

/**
 * Attempt to refresh the access token using the httpOnly refresh_token cookie.
 * De-duplicates concurrent refresh attempts.
 * Circuit breaker: after MAX_REFRESH_FAILURES consecutive failures, stops
 * retrying and redirects to login.
 */
async function refreshAccessToken() {
  if (refreshFailures >= MAX_REFRESH_FAILURES) {
    redirectToLogin();
    throw new Error('Session expired — too many refresh failures');
  }

  if (refreshPromise) return refreshPromise;

  // Backoff: wait longer after each consecutive failure
  if (refreshFailures > 0) {
    const delay = BACKOFF_BASE_MS * Math.pow(2, refreshFailures - 1);
    await new Promise((resolve) => setTimeout(resolve, delay));
  }

  refreshPromise = fetch(`${BASE}/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
    .then(async (res) => {
      if (!res.ok) {
        refreshFailures++;
        if (refreshFailures >= MAX_REFRESH_FAILURES) {
          redirectToLogin();
        }
        throw new Error('Session expired');
      }
      // Success — reset the failure counter
      refreshFailures = 0;
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

  // 429 = rate-limited, likely from refresh loop — treat as dead session
  if (res.status === 429) {
    redirectToLogin();
    throw new Error('Rate limited — session expired');
  }

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
