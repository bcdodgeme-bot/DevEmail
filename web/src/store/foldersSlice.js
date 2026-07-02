import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { apiFetch } from '../utils/api';

/** Fetch all mailbox folders across the user's accounts. */
export const fetchFolders = createAsyncThunk('folders/fetchFolders', async () => {
  return apiFetch('/folders');
});

const foldersSlice = createSlice({
  name: 'folders',
  initialState: {
    folders: [],
    status: 'idle', // idle | loading | succeeded | failed
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchFolders.pending, (state) => {
        state.status = 'loading';
      })
      .addCase(fetchFolders.fulfilled, (state, action) => {
        state.status = 'succeeded';
        state.folders = action.payload.folders || [];
      })
      .addCase(fetchFolders.rejected, (state) => {
        state.status = 'failed';
      });
  },
});

export const selectFolders = (state) => state.folders.folders;

/** Custom (user-created) folders only — the standard mailboxes
 *  (Inbox/Sent/Drafts/Junk/Trash) already have dedicated nav items. */
export const selectCustomFolders = (state) =>
  state.folders.folders.filter((f) => f.folder_type === 'custom');

export default foldersSlice.reducer;
