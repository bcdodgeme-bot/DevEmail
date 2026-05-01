import { apiFetch } from '../utils/api';

/** Per-category counts (all/people/bulk × unread/total) for the inbox view. */
export function fetchCategoryCounts({ accountId } = {}) {
  const params = new URLSearchParams();
  if (accountId) params.set('account_id', accountId);
  const qs = params.toString();
  return apiFetch(`/messages/category-counts${qs ? `?${qs}` : ''}`);
}

/** Manually move a message between People and Bulk. */
export function setMessageCategory(messageId, { category, applyToDomain = false, applyToExisting = false }) {
  return apiFetch(`/messages/${messageId}/category`, {
    method: 'PATCH',
    body: JSON.stringify({
      category,
      apply_to_domain: applyToDomain,
      apply_to_existing: applyToExisting,
    }),
  });
}

/** List sender classification rules. (Settings UI not built yet — wired for future.) */
export function listSenderClassifications({ page = 1, perPage = 50, accountId, category } = {}) {
  const params = new URLSearchParams({ page, per_page: perPage });
  if (accountId) params.set('account_id', accountId);
  if (category) params.set('category', category);
  return apiFetch(`/sender-classifications?${params}`);
}

export function deleteSenderClassification(id) {
  return apiFetch(`/sender-classifications/${id}`, { method: 'DELETE', raw: true });
}

export function updateSenderClassification(id, { category }) {
  return apiFetch(`/sender-classifications/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ category }),
  });
}
