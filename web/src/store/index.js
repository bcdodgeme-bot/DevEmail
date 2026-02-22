import { configureStore } from '@reduxjs/toolkit';
import authReducer from './authSlice';
import inboxReducer from './inboxSlice';
import accountsReducer from './accountsSlice';
import contactsReducer from './contactsSlice';
import calendarsReducer from './calendarsSlice';

export const store = configureStore({
  reducer: {
    auth: authReducer,
    inbox: inboxReducer,
    accounts: accountsReducer,
    contacts: contactsReducer,
    calendars: calendarsReducer,
  },
  devTools: import.meta.env.DEV,
});
