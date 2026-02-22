import { useState } from 'react';
import { User, Key, Palette, Bell, Shield, Info } from 'lucide-react';
import styles from './SettingsLayout.module.css';

const SECTIONS = [
  { key: 'accounts', label: 'Accounts', icon: User },
  { key: 'signatures', label: 'Signatures', icon: Key },
  { key: 'appearance', label: 'Appearance', icon: Palette },
  { key: 'notifications', label: 'Notifications', icon: Bell },
  { key: 'privacy', label: 'Privacy', icon: Shield },
  { key: 'about', label: 'About', icon: Info },
];

/**
 * SettingsLayout — sidebar nav + content panel.
 * children should be keyed by section key.
 * renderContent = (activeSection) => ReactNode
 */
export default function SettingsLayout({ activeSection, onSectionChange, children }) {
  return (
    <div className={styles.layout}>
      {/* Sidebar */}
      <nav className={styles.sidebar}>
        <h2 className={styles.sidebarTitle}>Settings</h2>
        <div className={styles.navList}>
          {SECTIONS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              className={`${styles.navItem} ${
                activeSection === key ? styles.navItemActive : ''
              }`}
              onClick={() => onSectionChange(key)}
              type="button"
            >
              <Icon size={16} />
              <span>{label}</span>
            </button>
          ))}
        </div>
      </nav>

      {/* Content */}
      <div className={styles.content}>{children}</div>
    </div>
  );
}
