import { configureStore } from '@reduxjs/toolkit';
import authReducer from './authSlice';
import inboxReducer from './inboxSlice';

export const store = configureStore({
  reducer: {
    auth: authReducer,
    inbox: inboxReducer,
    // accounts: accountsReducer,   — Phase 3
    // contacts: contactsReducer,   — Phase 4
    // calendars: calendarsReducer, — Phase 5
  },
  devTools: import.meta.env.DEV,
});
