import { createSlice, nanoid } from '@reduxjs/toolkit';

const toastSlice = createSlice({
  name: 'toast',
  initialState: {
    toasts: [],
  },
  reducers: {
    showToast: {
      reducer(state, action) {
        state.toasts.push(action.payload);
      },
      prepare({ message, undoKind = null, undoPayload = null, duration = 5000 }) {
        return {
          payload: {
            id: nanoid(),
            message,
            undoKind,
            undoPayload,
            duration,
            createdAt: Date.now(),
          },
        };
      },
    },
    dismissToast(state, action) {
      state.toasts = state.toasts.filter((t) => t.id !== action.payload);
    },
  },
});

export const { showToast, dismissToast } = toastSlice.actions;

export const selectToasts = (state) => state.toast.toasts;

export default toastSlice.reducer;
