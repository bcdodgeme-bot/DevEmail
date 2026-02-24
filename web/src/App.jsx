import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { selectIsAuthenticated } from './store/authSlice';
import { ROUTES } from './utils/constants';

// Layout
import AppShell from './components/layout/AppShell';

// Pages
import Login from './pages/Login';
import OAuthCallback from './pages/OAuthCallback';
import Inbox from './pages/Inbox';
import Contacts from './pages/Contacts';
import CalendarPage from './pages/Calendar';
import SettingsPage from './pages/Settings';

// Protected route wrapper
function ProtectedRoute({ children }) {
  const isAuthenticated = useSelector(selectIsAuthenticated);
  if (!isAuthenticated) {
    return <Navigate to={ROUTES.LOGIN} replace />;
  }
  return children;
}

// Public route wrapper (redirect if already logged in)
function PublicRoute({ children }) {
  const isAuthenticated = useSelector(selectIsAuthenticated);
  if (isAuthenticated) {
    return <Navigate to={ROUTES.INBOX} replace />;
  }
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route
          path={ROUTES.LOGIN}
          element={
            <PublicRoute>
              <Login />
            </PublicRoute>
          }
        />
        <Route path={ROUTES.OAUTH_CALLBACK} element={<OAuthCallback />} />

        {/* Protected routes — inside AppShell */}
        <Route
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        >
          {/* Inbox handles all mail views via route-based view switching */}
          <Route index element={<Inbox />} />
          <Route path="inbox/:threadId" element={<Inbox />} />
          <Route path={ROUTES.SENT} element={<Inbox />} />
          <Route path={ROUTES.DRAFTS} element={<Inbox />} />
          <Route path={ROUTES.TRASH} element={<Inbox />} />
          <Route path={ROUTES.CONTACTS} element={<Contacts />} />
          <Route path="contacts/:contactId" element={<Contacts />} />
          <Route path={ROUTES.CALENDAR} element={<CalendarPage />} />
          <Route path={ROUTES.SETTINGS} element={<SettingsPage />} />
        </Route>

        {/* Catch-all */}
        <Route path="*" element={<Navigate to={ROUTES.INBOX} replace />} />
      </Routes>
    </BrowserRouter>
  );
}
