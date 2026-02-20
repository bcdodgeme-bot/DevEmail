/**
 * Lightweight fetch wrapper that injects the JWT token.
 * Works with the authSlice token stored in Redux / localStorage.
 */

const BASE = '/api';

function getToken() {
  try {
    const persisted = localStorage.getItem('access_token');
    if (persisted) return persisted;
  } catch {
    /* SSR or restricted context */
  }
  return null;
}

export async function apiFetch(path, opts = {}) {
  const token = getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...opts.headers,
  };

  const res = await fetch(`${BASE}${path}`, { ...opts, headers });

  if (res.status === 401) {
    // Token expired — could dispatch logout here
    window.dispatchEvent(new CustomEvent('auth:expired'));
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API error ${res.status}`);
  }

  return res.json();
}
