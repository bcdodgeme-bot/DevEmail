import { useState, useEffect } from 'react';
import { Monitor, Moon, Sun } from 'lucide-react';
import styles from './AppearanceSettings.module.css';

const THEMES = [
  { key: 'dark', label: 'Dark', icon: Moon, description: 'Syntax Prime dark theme' },
  { key: 'light', label: 'Light', icon: Sun, description: 'Clean light theme' },
  { key: 'system', label: 'System', icon: Monitor, description: 'Match your OS setting' },
];

function getStoredTheme() {
  try {
    return localStorage.getItem('devemail-theme') || 'dark';
  } catch {
    return 'dark';
  }
}

function applyTheme(theme) {
  const root = document.documentElement;
  root.classList.remove('theme-dark', 'theme-light');

  if (theme === 'system') {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.classList.add(prefersDark ? 'theme-dark' : 'theme-light');
  } else {
    root.classList.add(`theme-${theme}`);
  }
}

export default function AppearanceSettings() {
  const [theme, setTheme] = useState(getStoredTheme);

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem('devemail-theme', theme);
  }, [theme]);

  // Listen for OS theme changes when in system mode
  useEffect(() => {
    if (theme !== 'system') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = () => applyTheme('system');
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [theme]);

  return (
    <div className={styles.container}>
      <h3 className={styles.title}>Appearance</h3>
      <p className={styles.subtitle}>Choose how DevEmail looks on your device</p>

      <div className={styles.themeGrid}>
        {THEMES.map(({ key, label, icon: Icon, description }) => (
          <button
            key={key}
            className={`${styles.themeCard} ${theme === key ? styles.themeCardActive : ''}`}
            onClick={() => setTheme(key)}
            type="button"
          >
            <div className={styles.themeIcon}>
              <Icon size={20} />
            </div>
            <span className={styles.themeLabel}>{label}</span>
            <span className={styles.themeDesc}>{description}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
