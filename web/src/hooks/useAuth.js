import { useSelector, useDispatch } from 'react-redux';
import {
  selectIsAuthenticated,
  selectUser,
  selectAuthLoading,
  selectAuthError,
  loginUser,
  registerUser,
  logout,
  logoutAll,
  fetchCurrentUser,
  clearError,
  setOAuthCredentials,
} from '../store/authSlice';

export function useAuth() {
  const dispatch = useDispatch();
  const isAuthenticated = useSelector(selectIsAuthenticated);
  const user = useSelector(selectUser);
  const isLoading = useSelector(selectAuthLoading);
  const error = useSelector(selectAuthError);

  const login = (email, password) => {
    return dispatch(loginUser({ email, password }));
  };

  const register = (email, password, displayName) => {
    return dispatch(registerUser({ email, password, displayName }));
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

  const dismissError = () => {
    dispatch(clearError());
  };

  // Handle OAuth callback — stores tokens + user from URL params into Redux and localStorage
  const handleOAuthCallback = ({ access_token, refresh_token, user }) => {
    dispatch(setOAuthCredentials({ access_token, refresh_token, user }));
  };

  return {
    isAuthenticated,
    user,
    isLoading,
    error,
    login,
    register,
    logout: handleLogout,
    logoutAll: handleLogoutAll,
    refreshUser,
    dismissError,
    handleOAuthCallback,
  };
}
