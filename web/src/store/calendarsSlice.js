import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { apiFetch } from '../utils/api';

/* ── Async thunks ─────────────────────────────────────── */

/** Fetch all calendars */
export const fetchCalendars = createAsyncThunk(
  'calendars/fetchCalendars',
  async () => {
    return apiFetch('/calendars');
  }
);

/** Fetch events within a date range */
export const fetchEvents = createAsyncThunk(
  'calendars/fetchEvents',
  async ({ start, end, calendarId } = {}) => {
    const params = new URLSearchParams();
    if (calendarId) params.set('calendar_id', calendarId);
    if (start) params.set('start', start);
    if (end) params.set('end', end);
    return apiFetch(`/calendars/events?${params}`);
  }
);

/** Create a new event */
export const createEvent = createAsyncThunk(
  'calendars/createEvent',
  async (data) => {
    return apiFetch('/calendars/events', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }
);

/** Update an event */
export const updateEvent = createAsyncThunk(
  'calendars/updateEvent',
  async ({ eventId, data }) => {
    return apiFetch(`/calendars/events/${eventId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }
);

/** Delete an event */
export const deleteEvent = createAsyncThunk(
  'calendars/deleteEvent',
  async (eventId) => {
    await apiFetch(`/calendars/events/${eventId}`, { method: 'DELETE' });
    return { eventId };
  }
);

/** Create a calendar */
export const createCalendar = createAsyncThunk(
  'calendars/createCalendar',
  async (data) => {
    return apiFetch('/calendars', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }
);

/** Sync calendars + events from Google (#6) */
export const syncCalendars = createAsyncThunk(
  'calendars/syncCalendars',
  async (_, { dispatch, getState }) => {
    const result = await apiFetch('/calendars/sync', { method: 'POST' });
    // Re-fetch calendars and events after sync
    await dispatch(fetchCalendars());
    const state = getState().calendars;
    const d = new Date(state.currentDate);
    const start = new Date(d.getFullYear(), d.getMonth() - 1, 1).toISOString();
    const end = new Date(d.getFullYear(), d.getMonth() + 2, 0).toISOString();
    await dispatch(fetchEvents({ start, end }));
    return result;
  }
);

/* ── Slice ────────────────────────────────────────────── */

const now = new Date();

const calendarsSlice = createSlice({
  name: 'calendars',
  initialState: {
    /* Calendars */
    calendars: [],
    calendarsStatus: 'idle',

    /* Events */
    events: [],
    eventsStatus: 'idle',
    eventsError: null,

    /* Sync */
    syncStatus: 'idle',
    syncError: null,

    /* View state */
    viewMode: 'month', // month | week | day
    currentDate: now.toISOString(),
    selectedDate: null,
    selectedEventId: null,
    selectedEvent: null,

    /* Editor */
    isEditorOpen: false,
    editingEvent: null, // null = new, object = editing
  },

  reducers: {
    setViewMode(state, action) {
      state.viewMode = action.payload;
    },
    setCurrentDate(state, action) {
      state.currentDate = action.payload;
    },
    setSelectedDate(state, action) {
      state.selectedDate = action.payload;
    },
    selectEvent(state, action) {
      state.selectedEventId = action.payload;
      state.selectedEvent = state.events.find((e) => e.id === action.payload) || null;
    },
    clearEventSelection(state) {
      state.selectedEventId = null;
      state.selectedEvent = null;
    },
    openEditor(state, action) {
      state.isEditorOpen = true;
      state.editingEvent = action.payload || null; // null = new event
    },
    closeEditor(state) {
      state.isEditorOpen = false;
      state.editingEvent = null;
    },
    navigateMonth(state, action) {
      const d = new Date(state.currentDate);
      d.setMonth(d.getMonth() + action.payload);
      state.currentDate = d.toISOString();
    },
    navigateWeek(state, action) {
      const d = new Date(state.currentDate);
      d.setDate(d.getDate() + 7 * action.payload);
      state.currentDate = d.toISOString();
    },
    navigateDay(state, action) {
      const d = new Date(state.currentDate);
      d.setDate(d.getDate() + action.payload);
      state.currentDate = d.toISOString();
    },
    goToToday(state) {
      state.currentDate = new Date().toISOString();
    },
  },

  extraReducers: (builder) => {
    /* ── fetchCalendars ── */
    builder
      .addCase(fetchCalendars.pending, (state) => {
        state.calendarsStatus = 'loading';
      })
      .addCase(fetchCalendars.fulfilled, (state, action) => {
        state.calendarsStatus = 'succeeded';
        state.calendars = action.payload.calendars;
      })
      .addCase(fetchCalendars.rejected, (state) => {
        state.calendarsStatus = 'failed';
      });

    /* ── fetchEvents ── */
    builder
      .addCase(fetchEvents.pending, (state) => {
        state.eventsStatus = 'loading';
        state.eventsError = null;
      })
      .addCase(fetchEvents.fulfilled, (state, action) => {
        state.eventsStatus = 'succeeded';
        state.events = action.payload.events;
      })
      .addCase(fetchEvents.rejected, (state, action) => {
        state.eventsStatus = 'failed';
        state.eventsError = action.error.message;
      });

    /* ── createEvent ── */
    builder.addCase(createEvent.fulfilled, (state, action) => {
      state.events.push(action.payload);
      state.isEditorOpen = false;
      state.editingEvent = null;
    });

    /* ── updateEvent ── */
    builder.addCase(updateEvent.fulfilled, (state, action) => {
      const idx = state.events.findIndex((e) => e.id === action.payload.id);
      if (idx !== -1) state.events[idx] = action.payload;
      if (state.selectedEvent?.id === action.payload.id) {
        state.selectedEvent = action.payload;
      }
      state.isEditorOpen = false;
      state.editingEvent = null;
    });

    /* ── deleteEvent ── */
    builder.addCase(deleteEvent.fulfilled, (state, action) => {
      state.events = state.events.filter((e) => e.id !== action.payload.eventId);
      if (state.selectedEventId === action.payload.eventId) {
        state.selectedEventId = null;
        state.selectedEvent = null;
      }
    });

    /* ── createCalendar ── */
    builder.addCase(createCalendar.fulfilled, (state, action) => {
      state.calendars.push(action.payload);
    });

    /* ── syncCalendars ── */
    builder
      .addCase(syncCalendars.pending, (state) => {
        state.syncStatus = 'loading';
        state.syncError = null;
      })
      .addCase(syncCalendars.fulfilled, (state) => {
        state.syncStatus = 'succeeded';
      })
      .addCase(syncCalendars.rejected, (state, action) => {
        state.syncStatus = 'failed';
        state.syncError = action.error.message;
      });
  },
});

/* ── Exports ──────────────────────────────────────────── */

export const {
  setViewMode,
  setCurrentDate,
  setSelectedDate,
  selectEvent,
  clearEventSelection,
  openEditor,
  closeEditor,
  navigateMonth,
  navigateWeek,
  navigateDay,
  goToToday,
} = calendarsSlice.actions;

export const selectCalendars = (state) => state.calendars.calendars;
export const selectCalendarsStatus = (state) => state.calendars.calendarsStatus;
export const selectEvents = (state) => state.calendars.events;
export const selectEventsStatus = (state) => state.calendars.eventsStatus;
export const selectViewMode = (state) => state.calendars.viewMode;
export const selectCurrentDate = (state) => state.calendars.currentDate;
export const selectSelectedDate = (state) => state.calendars.selectedDate;
export const selectSelectedEvent = (state) => state.calendars.selectedEvent;
export const selectIsEditorOpen = (state) => state.calendars.isEditorOpen;
export const selectEditingEvent = (state) => state.calendars.editingEvent;
export const selectSyncStatus = (state) => state.calendars.syncStatus;

export default calendarsSlice.reducer;
