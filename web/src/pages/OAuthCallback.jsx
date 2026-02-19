import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import styles from './Login.module.css';

export default function OAuthCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { handleOAuthCallback } = useAuth();
  const [error, setError] = useState(null);

  useEffect(() => {
    // The backend callback returns tokens as query params or in a JSON response.
    // We need to check what the backend actually returns.
    // Common pattern: backend redirects to frontend with tokens in URL fragment or params.
    const accessToken = searchParams.get('access_token');
    const refreshToken = searchParams.get('refresh_token');

    if (accessToken && refreshToken) {
      // Build user object from params if available
      const user = {
        id: searchParams.get('user_id'),
        email: searchParams.get('email'),
        display_name: searchParams.get('display_name'),
        avatar_url: searchParams.get('avatar_url'),
      };

      handleOAuthCallback({
        access_token: accessToken,
        refresh_token: refreshToken,
        user,
      });

      navigate('/', { replace: true });
    } else {
      // If no tokens in URL, the backend might redirect differently.
      // Show error or redirect to login.
      setError('Authentication failed. Please try again.');
      setTimeout(() => navigate('/login', { replace: true }), 3000);
    }
  }, [searchParams, handleOAuthCallback, navigate]);

  return (
    <div className={styles.page}>
      <div className={styles.ambientPurple} aria-hidden="true" />
      <div className={styles.grid} aria-hidden="true" />

      <div className={styles.card}>
        <div className={styles.logoContainer}>
          <img
            src="/logo.png"
            alt="DevEmail"
            className={styles.logo}
            width="80"
            height="80"
          />
        </div>

        {error ? (
          <>
            <h1 className={styles.title}>Authentication Error</h1>
            <p className={styles.hint}>{error}</p>
          </>
        ) : (
          <>
            <h1 className={styles.title}>Signing in...</h1>
            <p className={styles.hint}>Completing Google authentication</p>
          </>
        )}
      </div>
    </div>
  );
}
