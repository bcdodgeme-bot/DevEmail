import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { apiFetch } from '../utils/api';
import { showToast } from './toastSlice';

/* ── Async thunks ─────────────────────────────────────── */

/** Fetch thread list for any view (inbox, sent, drafts, trash) */
export const fetchThreads = createAsyncThunk(
  'inbox/fetchThreads',
  async ({ view = 'inbox', page = 1, perPage = 2000 } = {}) => {
    const endpoint = `/messages/${view}`;
    const params = new URLSearchParams({ page, per_page: perPage });
    return apiFetch(`${endpoint}?${params}`);
  }
);

/** Fetch full thread detail */
export const fetchThreadDetail = createAsyncThunk(
  'inbox/fetchThreadDetail',
  async (threadId) => {
    return apiFetch(`/messages/threads/${threadId}`);
  }
);

/** Toggle star on a thread */
export const toggleStar = createAsyncThunk(
  'inbox/toggleStar',
  async (threadId) => {
    const data = await apiFetch(`/messages/threads/${threadId}/star`, { method: 'PATCH' });
    return { threadId, ...data };
  }
);

/** Mark thread as read */
export const markRead = createAsyncThunk(
  'inbox/markRead',
  async (threadId) => {
    await apiFetch(`/messages/threads/${threadId}/read`, { method: 'PATCH' });
    return { threadId };
  }
);

/** Archive a thread */
export const archiveThread = createAsyncThunk(
  'inbox/archiveThread',
  async (threadId) => {
    await apiFetch(`/messages/threads/${threadId}/archive`, { method: 'PATCH' });
    return { threadId };
  }
);

/** Trash a thread — optimistically removes from list + fires Undo toast */
export const trashThread = createAsyncThunk(
  'inbox/trashThread',
  async (threadId, { getState, dispatch }) => {
    const state = getState();
    const threadSnapshot = state.inbox.threads.find((t) => t.id === threadId);
    const snapshotIndex = state.inbox.threads.findIndex((t) => t.id === threadId);
    await apiFetch(`/messages/threads/${threadId}/trash`, { method: 'PATCH' });
    dispatch(
      showToast({
        message: 'Moved to trash',
        undoKind: 'restoreThread',
        undoPayload: { threadId, threadSnapshot, snapshotIndex },
        duration: 5000,
      })
    );
    return { threadId };
  }
);

/** Undo a trash — restores the thread on the server + re-inserts locally */
export const restoreThread = createAsyncThunk(
  'inbox/restoreThread',
  async ({ threadId, threadSnapshot, snapshotIndex }) => {
    await apiFetch(`/messages/threads/${threadId}/restore`, { method: 'PATCH' });
    return { threadId, threadSnapshot, snapshotIndex };
  }
);

/** Mark thread as unread */
export const markUnread = createAsyncThunk(
  'inbox/markUnread',
  async (threadId) => {
    await apiFetch(`/messages/threads/${threadId}/unread`, { method: 'PATCH' });
    return { threadId };
  }
);

/** Snooze a thread until a specified time */
export const snoozeThread = createAsyncThunk(
  'inbox/snoozeThread',
  async ({ threadId, snoozedUntil }) => {
    const data = await apiFetch(`/messages/threads/${threadId}/snooze`, {
      method: 'POST',
      body: JSON.stringify({ snoozed_until: snoozedUntil }),
    });
    return { threadId, ...data };
  }
);

/** Unsnooze a thread */
export const unsnoozeThread = createAsyncThunk(
  'inbox/unsnoozeThread',
  async (threadId) => {
    const data = await apiFetch(`/messages/threads/${threadId}/unsnooze`, { method: 'PATCH' });
    return { threadId, ...data };
  }
);

/** Remove the given thread from the list and advance selection to the next
 *  thread at the same position (or the previous one if it was last). */
function advanceAfterRemoval(state, threadId) {
  const idx = state.threads.findIndex((t) => t.id === threadId);
  state.threads = state.threads.filter((t) => t.id !== threadId);
  if (state.selectedThreadId !== threadId) return;
  let nextId = null;
  if (state.threads.length > 0 && idx !== -1) {
    const nextIdx = idx < state.threads.length ? idx : state.threads.length - 1;
    nextId = state.threads[nextIdx]?.id || null;
  }
  state.selectedThreadId = nextId;
  state.threadDetail = null;
}

/* ── Slice ────────────────────────────────────────────── */

const inboxSlice = createSlice({
  name: 'inbox',
  initialState: {
    /* Thread list */
    threads: [],
    total: 0,
    page: 1,
    perPage: 50,
    view: 'inbox',          // inbox | sent | drafts | trash
    listStatus: 'idle',     // idle | loading | succeeded | failed
    listError: null,

    /* Selected thread detail */
    selectedThreadId: null,
    threadDetail: null,
    detailStatus: 'idle',
    detailError: null,

    /* Sync / connection tracking */
    lastSynced: null,        // ISO timestamp of last successful fetch
    isConnected: true,       // tracks whether last API call succeeded
  },

  reducers: {
    setView(state, action) {
      state.view = action.payload;
      state.selectedThreadId = null;
      state.threadDetail = null;
    },
    selectThread(state, action) {
      state.selectedThreadId = action.payload;
    },
    clearSelection(state) {
      state.selectedThreadId = null;
      state.threadDetail = null;
    },
  },

  extraReducers: (builder) => {
    /* ── fetchThreads ── */
    builder
      .addCase(fetchThreads.pending, (state) => {
        state.listStatus = 'loading';
        state.listError = null;
      })
      .addCase(fetchThreads.fulfilled, (state, action) => {
        state.listStatus = 'succeeded';
        state.threads = action.payload.threads;
        state.total = action.payload.total;
        state.page = action.payload.page;
        state.perPage = action.payload.per_page;
        state.lastSynced = new Date().toISOString();
        state.isConnected = true;
      })
      .addCase(fetchThreads.rejected, (state, action) => {
        state.listStatus = 'failed';
        state.listError = action.error.message;
        state.isConnected = false;
      });

    /* ── fetchThreadDetail ── */
    builder
      .addCase(fetchThreadDetail.pending, (state) => {
        state.detailStatus = 'loading';
        state.detailError = null;
      })
      .addCase(fetchThreadDetail.fulfilled, (state, action) => {
        state.detailStatus = 'succeeded';
        state.threadDetail = action.payload;
        state.isConnected = true;
      })
      .addCase(fetchThreadDetail.rejected, (state, action) => {
        state.detailStatus = 'failed';
        state.detailError = action.error.message;
      });

    /* ── toggleStar ── */
    builder.addCase(toggleStar.fulfilled, (state, action) => {
      const { threadId, is_starred } = action.payload;
      const t = state.threads.find((t) => t.id === threadId);
      if (t) t.is_starred = is_starred;
      if (state.threadDetail?.id === threadId) {
        state.threadDetail.is_starred = is_starred;
      }
    });

    /* ── markRead ── */
    builder.addCase(markRead.fulfilled, (state, action) => {
      const { threadId } = action.payload;
      const t = state.threads.find((t) => t.id === threadId);
      if (t) t.has_unread = false;
    });

    /* ── markUnread ── */
    builder.addCase(markUnread.fulfilled, (state, action) => {
      const { threadId } = action.payload;
      const t = state.threads.find((t) => t.id === threadId);
      if (t) t.has_unread = true;
    });

    /* ── archiveThread — remove from list, advance to next ── */
    builder.addCase(archiveThread.fulfilled, (state, action) => {
      advanceAfterRemoval(state, action.payload.threadId);
    });

    /* ── trashThread — remove from list, advance to next ── */
    builder.addCase(trashThread.fulfilled, (state, action) => {
      advanceAfterRemoval(state, action.payload.threadId);
    });

    /* ── restoreThread — re-insert at original position ── */
    builder.addCase(restoreThread.fulfilled, (state, action) => {
      const { threadId, threadSnapshot, snapshotIndex } = action.payload;
      if (!threadSnapshot) return;
      if (state.threads.some((t) => t.id === threadId)) return;
      const insertAt = Math.min(
        Math.max(snapshotIndex ?? 0, 0),
        state.threads.length
      );
      state.threads.splice(insertAt, 0, threadSnapshot);
    });

    /* ── snoozeThread — remove from inbox list ── */
    builder.addCase(snoozeThread.fulfilled, (state, action) => {
      const { threadId, is_snoozed, snoozed_until } = action.payload;
      // Remove from inbox since snoozed threads are hidden
      state.threads = state.threads.filter((t) => t.id !== threadId);
      if (state.threadDetail?.id === threadId) {
        state.threadDetail.is_snoozed = is_snoozed;
        state.threadDetail.snoozed_until = snoozed_until;
      }
      if (state.selectedThreadId === threadId) {
        state.selectedThreadId = null;
        state.threadDetail = null;
      }
    });

    /* ── unsnoozeThread ── */
    builder.addCase(unsnoozeThread.fulfilled, (state, action) => {
      const { threadId } = action.payload;
      const t = state.threads.find((t) => t.id === threadId);
      if (t) {
        t.is_snoozed = false;
        t.snoozed_until = null;
      }
      if (state.threadDetail?.id === threadId) {
        state.threadDetail.is_snoozed = false;
        state.threadDetail.snoozed_until = null;
      }
    });
  },
});

/* ── Exports ──────────────────────────────────────────── */

export const { setView, selectThread, clearSelection } = inboxSlice.actions;

export const selectThreads = (state) => state.inbox.threads;
export const selectListStatus = (state) => state.inbox.listStatus;
export const selectListError = (state) => state.inbox.listError;
export const selectView = (state) => state.inbox.view;
export const selectSelectedThreadId = (state) => state.inbox.selectedThreadId;
export const selectThreadDetail = (state) => state.inbox.threadDetail;
export const selectDetailStatus = (state) => state.inbox.detailStatus;
export const selectLastSynced = (state) => state.inbox.lastSynced;
export const selectIsConnected = (state) => state.inbox.isConnected;
export const selectUnreadCount = (state) =>
  state.inbox.threads.filter((t) => t.has_unread).length;

export default inboxSlice.reducer;
