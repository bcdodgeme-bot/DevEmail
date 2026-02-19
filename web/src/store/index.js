import { configureStore } from '@reduxjs/toolkit';
import authReducer from './authSlice';

export const store = configureStore({
  reducer: {
    auth: authReducer,
    // accounts: accountsReducer,   — Phase 2
    // threads: threadsReducer,     — Phase 2
    // messages: messagesReducer,   — Phase 3
    // contacts: contactsReducer,   — Phase 4
    // calendars: calendarsReducer, — Phase 5
  },
  devTools: import.meta.env.DEV,
});
