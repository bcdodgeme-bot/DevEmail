import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { apiFetch } from '../utils/api';

/* ── Async thunks ─────────────────────────────────────── */

/** Fetch all linked email accounts (includes signatures) */
export const fetchAccounts = createAsyncThunk(
  'accounts/fetchAccounts',
  async () => {
    return apiFetch('/accounts');
  }
);

/** Link a Stalwart account */
export const linkStalwart = createAsyncThunk(
  'accounts/linkStalwart',
  async (data) => {
    return apiFetch('/accounts/stalwart', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }
);

/** Update account settings */
export const updateAccount = createAsyncThunk(
  'accounts/updateAccount',
  async ({ accountId, data }) => {
    return apiFetch(`/accounts/${accountId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }
);

/** Unlink an account */
export const unlinkAccount = createAsyncThunk(
  'accounts/unlinkAccount',
  async (accountId) => {
    await apiFetch(`/accounts/${accountId}`, { method: 'DELETE' });
    return { accountId };
  }
);

/* ── Slice ────────────────────────────────────────────── */

const accountsSlice = createSlice({
  name: 'accounts',
  initialState: {
    accounts: [],
    total: 0,
    status: 'idle', // idle | loading | succeeded | failed
    error: null,
  },
  reducers: {},
  extraReducers: (builder) => {
    /* ── fetchAccounts ── */
    builder
      .addCase(fetchAccounts.pending, (state) => {
        state.status = 'loading';
        state.error = null;
      })
      .addCase(fetchAccounts.fulfilled, (state, action) => {
        state.status = 'succeeded';
        state.accounts = action.payload.accounts;
        state.total = action.payload.total;
      })
      .addCase(fetchAccounts.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.error.message;
      });

    /* ── linkStalwart ── */
    builder.addCase(linkStalwart.fulfilled, (state, action) => {
      state.accounts.push(action.payload);
      state.total += 1;
    });

    /* ── updateAccount ── */
    builder.addCase(updateAccount.fulfilled, (state, action) => {
      const idx = state.accounts.findIndex((a) => a.id === action.payload.id);
      if (idx !== -1) state.accounts[idx] = action.payload;
    });

    /* ── unlinkAccount ── */
    builder.addCase(unlinkAccount.fulfilled, (state, action) => {
      state.accounts = state.accounts.filter((a) => a.id !== action.payload.accountId);
      state.total -= 1;
    });
  },
});

/* ── Selectors ────────────────────────────────────────── */

export const selectAccounts = (state) => state.accounts.accounts;
export const selectAccountsStatus = (state) => state.accounts.status;
export const selectDefaultAccount = (state) =>
  state.accounts.accounts.find((a) => a.is_default) || state.accounts.accounts[0] || null;

export default accountsSlice.reducer;
