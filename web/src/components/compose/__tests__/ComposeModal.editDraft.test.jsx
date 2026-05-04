/**
 * Phase 9 D bug repro: opening the compose modal with an `editDraft` prop
 * should fetch the draft's attachments via attachmentsAPI.list() and
 * render each item in the modal's attachment list.
 *
 * Mounting ComposeModal directly requires a Redux Provider (the modal uses
 * useSelector for accounts) and mocks for the api/compose module so the
 * fetch doesn't go to the network.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

// Mock react-redux so the modal's useSelector / useDispatch don't need a
// Provider. The modal only reads accounts; we return the minimum needed.
vi.mock('react-redux', () => ({
  useSelector: (sel) => sel({
    accounts: { accounts: [], total: 0, status: 'succeeded', error: null },
  }),
  useDispatch: () => vi.fn(),
}));

// Mock the API module BEFORE importing the modal, so the modal's import
// captures the mocked attachmentsAPI / composeAPI.
vi.mock('../../../api/compose', async () => {
  return {
    composeAPI: {
      send: vi.fn().mockResolvedValue({ message_id: 'new-msg' }),
      sendWithAttachments: vi.fn().mockResolvedValue({ message_id: 'new-msg' }),
      sendExistingDraft: vi.fn().mockResolvedValue({ message_id: 'new-msg' }),
      updateDraft: vi.fn().mockResolvedValue({}),
      searchContacts: vi.fn().mockResolvedValue({ contacts: [] }),
    },
    attachmentsAPI: {
      getLimits: vi.fn().mockResolvedValue({ max_bytes: 25 * 1024 * 1024 }),
      list: vi.fn(),
      upload: vi.fn(),
      delete: vi.fn().mockResolvedValue({}),
      downloadUrl: (mid, aid) => `/api/messages/${mid}/attachments/${aid}/download`,
    },
  };
});

// Other module-level deps that the modal pulls in.
vi.mock('../../../utils/api', () => ({
  apiFetch: vi.fn().mockResolvedValue({ contacts: [] }),
}));

// Stub the inbox slice's archiveThread action (the modal dispatches it on
// Send success — irrelevant here but the import has to resolve).
vi.mock('../../../store/inboxSlice', () => ({
  archiveThread: () => ({ type: 'inbox/archiveThread/stub' }),
}));

vi.mock('../../../store/accountsSlice', () => ({
  fetchAccounts: () => ({ type: 'accounts/fetchAccounts/stub' }),
  selectAccounts: (state) => state.accounts.accounts,
  selectDefaultAccount: (state) => state.accounts.accounts[0] || null,
}));

import ComposeModal from '../ComposeModal';
import { attachmentsAPI } from '../../../api/compose';


function renderModal(props = {}) {
  return render(<ComposeModal isOpen onClose={() => {}} {...props} />);
}


describe('ComposeModal — editDraft hydration (Phase 9 D bug repro)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders existing attachments fetched from the server', async () => {
    const draft = {
      id: 'draft-uuid',
      account_id: 'acc-1',
      to_addresses: [{ address: 'bob@example.com', name: 'Bob' }],
      cc_addresses: [],
      bcc_addresses: [],
      subject: 'Hi',
      body_text: 'Hello',
      body_html: '',
    };

    attachmentsAPI.list.mockResolvedValueOnce([
      {
        id: 'att-1',
        filename: 'Carl_Dodge_Resume.pdf',
        content_type: 'application/pdf',
        size_bytes: 12345,
      },
    ]);

    renderModal({ editDraft: draft });

    // The fetch is async (effect kicks off list() inside an IIFE). Use
    // waitFor so we let the resolved promise propagate + a re-render
    // happen.
    await waitFor(() => {
      expect(screen.getByText('Carl_Dodge_Resume.pdf')).toBeInTheDocument();
    });

    // Confirm the request actually hit attachmentsAPI.list with the right id.
    expect(attachmentsAPI.list).toHaveBeenCalledWith('draft-uuid');
  });

  it('does not fetch attachments when editDraft is null', async () => {
    renderModal({ editDraft: null });
    // Give effects a chance to settle.
    await new Promise((r) => setTimeout(r, 0));
    expect(attachmentsAPI.list).not.toHaveBeenCalled();
  });
});
