import { apiFetch } from '../utils/api';

export const apiKeysAPI = {
  list: () => apiFetch('/keys'),
  create: (name) =>
    apiFetch('/keys', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  revoke: (id) => apiFetch(`/keys/${id}`, { method: 'DELETE' }),
};
