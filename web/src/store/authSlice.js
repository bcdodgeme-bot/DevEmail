import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { authAPI } from '../api/auth';

// Check localStorage for existing session
const storedAccessToken = localStorage.getItem('access_token');
const storedRefreshToken = localStorage.getItem('refresh_token');
const storedUser = localStorage.getItem('user');

// Async thunks
export const fetchCurrentUser = createAsyncThunk(
  'auth/fetchCurrentUser',
  async (_, { rejectWithValue }) => {
    try {
      const user = await authAPI.me();
      return user;
    } catch (err) {
      return rejectWithValue(err.response?.data?.detail || 'Failed to fetch user');
    }
  }
);

export const refreshTokens = createAsyncThunk(
  'auth/refreshTokens',
  async (_, { getState, rejectWithValue }) => {
    try {
      const { auth } = getState();
      const data = await authAPI.refresh(auth.refreshToken);
      return data;
    } catch (err) {
      return rejectWithValue('Session expired');
    }
  }
);

export const logout = createAsyncThunk(
  'auth/logout',
  async (_, { getState }) => {
    const { auth } = getState();
    try {
      await authAPI.logout(auth.refreshToken);
    } catch {
      // Logout even if the API call fails
    }
  }
);

export const logoutAll = createAsyncThunk(
  'auth/logoutAll',
  async () => {
    await authAPI.logoutAll();
  }
);

const authSlice = createSlice({
  name: 'auth',
  initialState: {
    accessToken: storedAccessToken || null,
    refreshToken: storedRefreshToken || null,
    user: storedUser ? JSON.parse(storedUser) : null,
    isAuthenticated: !!storedAccessToken,
    isLoading: false,
    error: null,
  },
  reducers: {
    // Called after Google OAuth callback
    setCredentials: (state, action) => {
      const { access_token, refresh_token, user } = action.payload;
      state.accessToken = access_token;
      state.refreshToken = refresh_token;
      state.user = user;
      state.isAuthenticated = true;
      state.error = null;

      localStorage.setItem('access_token', access_token);
      localStorage.setItem('refresh_token', refresh_token);
      localStorage.setItem('user', JSON.stringify(user));
    },
    clearCredentials: (state) => {
      state.accessToken = null;
      state.refreshToken = null;
      state.user = null;
      state.isAuthenticated = false;
      state.error = null;

      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
    },
    updateTokens: (state, action) => {
      const { access_token, refresh_token } = action.payload;
      state.accessToken = access_token;
      state.refreshToken = refresh_token;

      localStorage.setItem('access_token', access_token);
      localStorage.setItem('refresh_token', refresh_token);
    },
  },
  extraReducers: (builder) => {
    builder
      // Fetch current user
      .addCase(fetchCurrentUser.pending, (state) => {
        state.isLoading = true;
      })
      .addCase(fetchCurrentUser.fulfilled, (state, action) => {
        state.user = action.payload;
        state.isLoading = false;
        localStorage.setItem('user', JSON.stringify(action.payload));
      })
      .addCase(fetchCurrentUser.rejected, (state) => {
        state.isLoading = false;
      })

      // Refresh tokens
      .addCase(refreshTokens.fulfilled, (state, action) => {
        const { access_token, refresh_token } = action.payload;
        state.accessToken = access_token;
        state.refreshToken = refresh_token;
        localStorage.setItem('access_token', access_token);
        localStorage.setItem('refresh_token', refresh_token);
      })
      .addCase(refreshTokens.rejected, (state) => {
        // Refresh failed — force logout
        state.accessToken = null;
        state.refreshToken = null;
        state.user = null;
        state.isAuthenticated = false;
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
      })

      // Logout
      .addCase(logout.fulfilled, (state) => {
        state.accessToken = null;
        state.refreshToken = null;
        state.user = null;
        state.isAuthenticated = false;
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
      })

      // Logout all
      .addCase(logoutAll.fulfilled, (state) => {
        state.accessToken = null;
        state.refreshToken = null;
        state.user = null;
        state.isAuthenticated = false;
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
      });
  },
});

export const { setCredentials, clearCredentials, updateTokens } = authSlice.actions;

// Selectors
export const selectIsAuthenticated = (state) => state.auth.isAuthenticated;
export const selectUser = (state) => state.auth.user;
export const selectAccessToken = (state) => state.auth.accessToken;
export const selectAuthLoading = (state) => state.auth.isLoading;

export default authSlice.reducer;
