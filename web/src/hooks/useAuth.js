import { useSelector, useDispatch } from 'react-redux';
import {
  selectIsAuthenticated,
  selectUser,
  selectAuthLoading,
  setCredentials,
  logout,
  logoutAll,
  fetchCurrentUser,
} from '../store/authSlice';
import { authAPI } from '../api/auth';

export function useAuth() {
  const dispatch = useDispatch();
  const isAuthenticated = useSelector(selectIsAuthenticated);
  const user = useSelector(selectUser);
  const isLoading = useSelector(selectAuthLoading);

  const login = () => {
    // Redirect to Google OAuth
    window.location.href = authAPI.getLoginUrl();
  };

  const handleOAuthCallback = (params) => {
    // Called from the OAuth callback route with token data
    dispatch(setCredentials(params));
  };

  const handleLogout = () => {
    dispatch(logout());
  };

  const handleLogoutAll = () => {
    dispatch(logoutAll());
  };

  const refreshUser = () => {
    dispatch(fetchCurrentUser());
  };

  return {
    isAuthenticated,
    user,
    isLoading,
    login,
    handleOAuthCallback,
    logout: handleLogout,
    logoutAll: handleLogoutAll,
    refreshUser,
  };
}
