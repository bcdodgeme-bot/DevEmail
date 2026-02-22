import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { apiFetch } from '../utils/api';

/* ── Async thunks ─────────────────────────────────────── */

/** Fetch contacts with search/pagination */
export const fetchContacts = createAsyncThunk(
  'contacts/fetchContacts',
  async ({ search, page = 1, perPage = 50, tag, favoritesOnly } = {}) => {
    const params = new URLSearchParams({ page, per_page: perPage });
    if (search) params.set('search', search);
    if (tag) params.set('tag', tag);
    if (favoritesOnly) params.set('is_favorite', 'true');
    return apiFetch(`/contacts?${params}`);
  }
);

/** Fetch full contact detail */
export const fetchContactDetail = createAsyncThunk(
  'contacts/fetchContactDetail',
  async (contactId) => {
    return apiFetch(`/contacts/${contactId}`);
  }
);

/** Create a new contact */
export const createContact = createAsyncThunk(
  'contacts/createContact',
  async (data) => {
    return apiFetch('/contacts', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }
);

/** Update a contact */
export const updateContact = createAsyncThunk(
  'contacts/updateContact',
  async ({ contactId, data }) => {
    return apiFetch(`/contacts/${contactId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }
);

/** Delete a contact */
export const deleteContact = createAsyncThunk(
  'contacts/deleteContact',
  async (contactId) => {
    await apiFetch(`/contacts/${contactId}`, { method: 'DELETE' });
    return { contactId };
  }
);

/** Toggle favorite */
export const toggleFavorite = createAsyncThunk(
  'contacts/toggleFavorite',
  async (contactId) => {
    const data = await apiFetch(`/contacts/${contactId}/favorite`, { method: 'PATCH' });
    return { contactId, ...data };
  }
);

/* ── Slice ────────────────────────────────────────────── */

const contactsSlice = createSlice({
  name: 'contacts',
  initialState: {
    /* List */
    contacts: [],
    total: 0,
    page: 1,
    perPage: 50,
    search: '',
    listStatus: 'idle',
    listError: null,

    /* Selected detail */
    selectedContactId: null,
    contactDetail: null,
    detailStatus: 'idle',
    detailError: null,

    /* Editing */
    isEditing: false,
  },

  reducers: {
    setSearch(state, action) {
      state.search = action.payload;
    },
    selectContact(state, action) {
      state.selectedContactId = action.payload;
      state.isEditing = false;
    },
    clearContactSelection(state) {
      state.selectedContactId = null;
      state.contactDetail = null;
      state.isEditing = false;
    },
    setEditing(state, action) {
      state.isEditing = action.payload;
    },
  },

  extraReducers: (builder) => {
    /* ── fetchContacts ── */
    builder
      .addCase(fetchContacts.pending, (state) => {
        state.listStatus = 'loading';
        state.listError = null;
      })
      .addCase(fetchContacts.fulfilled, (state, action) => {
        state.listStatus = 'succeeded';
        state.contacts = action.payload.contacts;
        state.total = action.payload.total;
        state.page = action.payload.page;
        state.perPage = action.payload.per_page;
      })
      .addCase(fetchContacts.rejected, (state, action) => {
        state.listStatus = 'failed';
        state.listError = action.error.message;
      });

    /* ── fetchContactDetail ── */
    builder
      .addCase(fetchContactDetail.pending, (state) => {
        state.detailStatus = 'loading';
        state.detailError = null;
      })
      .addCase(fetchContactDetail.fulfilled, (state, action) => {
        state.detailStatus = 'succeeded';
        state.contactDetail = action.payload;
      })
      .addCase(fetchContactDetail.rejected, (state, action) => {
        state.detailStatus = 'failed';
        state.detailError = action.error.message;
      });

    /* ── createContact ── */
    builder.addCase(createContact.fulfilled, (state, action) => {
      state.contacts.unshift(action.payload);
      state.total += 1;
      state.selectedContactId = action.payload.id;
      state.contactDetail = action.payload;
      state.isEditing = false;
    });

    /* ── updateContact ── */
    builder.addCase(updateContact.fulfilled, (state, action) => {
      const idx = state.contacts.findIndex((c) => c.id === action.payload.id);
      if (idx !== -1) state.contacts[idx] = action.payload;
      if (state.contactDetail?.id === action.payload.id) {
        state.contactDetail = action.payload;
      }
      state.isEditing = false;
    });

    /* ── deleteContact ── */
    builder.addCase(deleteContact.fulfilled, (state, action) => {
      state.contacts = state.contacts.filter((c) => c.id !== action.payload.contactId);
      state.total -= 1;
      if (state.selectedContactId === action.payload.contactId) {
        state.selectedContactId = null;
        state.contactDetail = null;
      }
    });

    /* ── toggleFavorite ── */
    builder.addCase(toggleFavorite.fulfilled, (state, action) => {
      const { contactId, is_favorite } = action.payload;
      const c = state.contacts.find((c) => c.id === contactId);
      if (c) c.is_favorite = is_favorite;
      if (state.contactDetail?.id === contactId) {
        state.contactDetail.is_favorite = is_favorite;
      }
    });
  },
});

/* ── Exports ──────────────────────────────────────────── */

export const { setSearch, selectContact, clearContactSelection, setEditing } =
  contactsSlice.actions;

export const selectContacts = (state) => state.contacts.contacts;
export const selectContactsTotal = (state) => state.contacts.total;
export const selectContactsListStatus = (state) => state.contacts.listStatus;
export const selectContactsSearch = (state) => state.contacts.search;
export const selectSelectedContactId = (state) => state.contacts.selectedContactId;
export const selectContactDetail = (state) => state.contacts.contactDetail;
export const selectContactDetailStatus = (state) => state.contacts.detailStatus;
export const selectIsEditing = (state) => state.contacts.isEditing;

export default contactsSlice.reducer;
