import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import styles from './Login.module.css';

export default function OAuthCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { handleOAuthCallback } = useAuth();

  useEffect(() => {
    // Backend has already set httpOnly cookies via the OAuth callback redirect.
    // Re-initialize auth state from those cookies, then redirect to the app.
    const error = searchParams.get('error');
    if (error) {
      navigate('/login?error=oauth_failed', { replace: true });
      return;
    }

    handleOAuthCallback();
    navigate('/', { replace: true });
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
        <h1 className={styles.title}>Signing in...</h1>
        <p className={styles.hint}>Completing Google authentication</p>
      </div>
    </div>
  );
}
