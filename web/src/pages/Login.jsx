import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { Eye, EyeOff, ArrowRight, Loader2 } from 'lucide-react';
import styles from './Login.module.css';

export default function Login() {
  const { login, register, isLoading, error, dismissError } = useAuth();

  const [mode, setMode] = useState('login'); // 'login' or 'register'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    dismissError();

    if (mode === 'login') {
      login(email, password);
    } else {
      register(email, password, displayName || null);
    }
  };

  const toggleMode = () => {
    setMode(mode === 'login' ? 'register' : 'login');
    dismissError();
  };

  return (
    <div className={styles.page}>
      {/* Ambient glow effects */}
      <div className={styles.ambientPurple} aria-hidden="true" />
      <div className={styles.ambientAmber} aria-hidden="true" />

      {/* Grid overlay */}
      <div className={styles.grid} aria-hidden="true" />

      <div className={styles.card}>
        {/* Logo */}
        <div className={styles.logoContainer}>
          <img
            src="/logo.png"
            alt="DevEmail"
            className={styles.logo}
            width="80"
            height="80"
          />
          <div className={styles.logoGlow} aria-hidden="true" />
        </div>

        {/* Title */}
        <h1 className={styles.title}>DevEmail</h1>
        <p className={styles.subtitle}>Unified Inbox & PIM</p>
        <p className={styles.network}>Part of the Syntax Network</p>

        {/* Form */}
        <form className={styles.form} onSubmit={handleSubmit}>
          {/* Display name (register only) */}
          {mode === 'register' && (
            <div className={styles.field}>
              <label className={styles.label} htmlFor="displayName">
                Display Name
              </label>
              <input
                id="displayName"
                type="text"
                className={styles.input}
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Carl"
                autoComplete="name"
              />
            </div>
          )}

          <div className={styles.field}>
            <label className={styles.label} htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              className={styles.input}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@mail.damnitcarl.dev"
              required
              autoComplete="email"
              autoFocus
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="password">
              Password
            </label>
            <div className={styles.passwordWrap}>
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                className={styles.input}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                minLength={6}
              />
              <button
                type="button"
                className={styles.eyeButton}
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          {/* Error message */}
          {error && (
            <div className={styles.error}>{error}</div>
          )}

          {/* Submit */}
          <button
            type="submit"
            className={styles.submitButton}
            disabled={isLoading || !email || !password}
          >
            {isLoading ? (
              <Loader2 size={18} className={styles.spinner} />
            ) : (
              <>
                <span>{mode === 'login' ? 'Sign In' : 'Create Account'}</span>
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>

        {/* Toggle mode */}
        <p className={styles.toggle}>
          {mode === 'login' ? "Don't have an account?" : 'Already have an account?'}{' '}
          <button type="button" className={styles.toggleLink} onClick={toggleMode}>
            {mode === 'login' ? 'Create one' : 'Sign in'}
          </button>
        </p>
      </div>

      {/* Version */}
      <span className={styles.version}>v0.1.0</span>
    </div>
  );
}
