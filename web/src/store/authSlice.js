import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { authAPI } from '../api/auth';

// Check localStorage for existing session
const storedAccessToken = localStorage.getItem('access_token');
const storedRefreshToken = localStorage.getItem('refresh_token');
const storedUser = localStorage.getItem('user');

// === Async Thunks ===

export const loginUser = createAsyncThunk(
  'auth/loginUser',
  async ({ email, password }, { rejectWithValue }) => {
    try {
      const tokenData = await authAPI.login(email, password);
      // Fetch user info with the new token
      localStorage.setItem('access_token', tokenData.access_token);
      const user = await authAPI.me();
      return { ...tokenData, user };
    } catch (err) {
      return rejectWithValue(err.message || 'Invalid email or password');
    }
  }
);

export const registerUser = createAsyncThunk(
  'auth/registerUser',
  async ({ email, password, displayName }, { rejectWithValue }) => {
    try {
      const tokenData = await authAPI.register(email, password, displayName);
      localStorage.setItem('access_token', tokenData.access_token);
      const user = await authAPI.me();
      return { ...tokenData, user };
    } catch (err) {
      return rejectWithValue(err.message || 'Registration failed');
    }
  }
);

export const fetchCurrentUser = createAsyncThunk(
  'auth/fetchCurrentUser',
  async (_, { rejectWithValue }) => {
    try {
      return await authAPI.me();
    } catch (err) {
      return rejectWithValue(err.message || 'Failed to fetch user');
    }
  }
);

export const refreshTokens = createAsyncThunk(
  'auth/refreshTokens',
  async (_, { getState, rejectWithValue }) => {
    try {
      const { auth } = getState();
      return await authAPI.refresh(auth.refreshToken);
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

// Helper to save auth state to localStorage
function persistAuth(state) {
  localStorage.setItem('access_token', state.accessToken);
  localStorage.setItem('refresh_token', state.refreshToken);
  if (state.user) {
    localStorage.setItem('user', JSON.stringify(state.user));
  }
}

function clearAuth(state) {
  state.accessToken = null;
  state.refreshToken = null;
  state.user = null;
  state.isAuthenticated = false;
  state.error = null;
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
}

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
    updateTokens: (state, action) => {
      const { access_token, refresh_token } = action.payload;
      state.accessToken = access_token;
      state.refreshToken = refresh_token;
      localStorage.setItem('access_token', access_token);
      localStorage.setItem('refresh_token', refresh_token);
    },
    clearError: (state) => {
      state.error = null;
    },
    // Synchronous reducer for OAuth callback — tokens + user arrive via URL params
    setOAuthCredentials: (state, action) => {
      const { access_token, refresh_token, user } = action.payload;
      state.accessToken = access_token;
      state.refreshToken = refresh_token;
      state.user = user;
      state.isAuthenticated = true;
      state.isLoading = false;
      state.error = null;
      persistAuth(state);
    },
  },
  extraReducers: (builder) => {
    builder
      // Login
      .addCase(loginUser.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(loginUser.fulfilled, (state, action) => {
        const { access_token, refresh_token, user } = action.payload;
        state.accessToken = access_token;
        state.refreshToken = refresh_token;
        state.user = user;
        state.isAuthenticated = true;
        state.isLoading = false;
        state.error = null;
        persistAuth(state);
      })
      .addCase(loginUser.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload;
      })

      // Register
      .addCase(registerUser.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(registerUser.fulfilled, (state, action) => {
        const { access_token, refresh_token, user } = action.payload;
        state.accessToken = access_token;
        state.refreshToken = refresh_token;
        state.user = user;
        state.isAuthenticated = true;
        state.isLoading = false;
        state.error = null;
        persistAuth(state);
      })
      .addCase(registerUser.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload;
      })

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
        clearAuth(state);
      })

      // Logout
      .addCase(logout.fulfilled, (state) => {
        clearAuth(state);
      })

      // Logout all
      .addCase(logoutAll.fulfilled, (state) => {
        clearAuth(state);
      });
  },
});

export const { updateTokens, clearError, setOAuthCredentials } = authSlice.actions;
export const { clearCredentials } = { clearCredentials: authSlice.actions.clearError }; // alias for client.js compatibility

// Selectors
export const selectIsAuthenticated = (state) => state.auth.isAuthenticated;
export const selectUser = (state) => state.auth.user;
export const selectAccessToken = (state) => state.auth.accessToken;
export const selectAuthLoading = (state) => state.auth.isLoading;
export const selectAuthError = (state) => state.auth.error;

export default authSlice.reducer;
