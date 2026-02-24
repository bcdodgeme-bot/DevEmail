import { useState, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { fetchAccounts, selectAccountsStatus } from '../store/accountsSlice';
import SettingsLayout from '../components/settings/SettingsLayout';
import AccountManager from '../components/settings/AccountManager';
import SignatureEditor from '../components/settings/SignatureEditor';
import AppearanceSettings from '../components/settings/AppearanceSettings';
import NotificationSettings from '../components/settings/NotificationSettings';
import PrivacySettings from '../components/settings/PrivacySettings';
import styles from './Settings.module.css';

export default function Settings() {
  const dispatch = useDispatch();
  const accountsStatus = useSelector(selectAccountsStatus);
  const [activeSection, setActiveSection] = useState('accounts');

  /* Ensure accounts are loaded for settings */
  useEffect(() => {
    if (accountsStatus === 'idle') {
      dispatch(fetchAccounts());
    }
  }, [accountsStatus, dispatch]);

  const renderContent = () => {
    switch (activeSection) {
      case 'accounts':
        return <AccountManager />;
      case 'signatures':
        return <SignatureEditor />;
      case 'appearance':
        return <AppearanceSettings />;
      case 'notifications':
        return <NotificationSettings />;
      case 'privacy':
        return <PrivacySettings />;
      case 'about':
        return (
          <div className={styles.about}>
            <h3 className={styles.aboutTitle}>DevEmail</h3>
            <p className={styles.aboutVersion}>v1.0.0</p>
            <p className={styles.aboutText}>
              A unified email inbox and personal information management system.
              Part of the Syntax ecosystem.
            </p>
            <div className={styles.aboutLinks}>
              <span className={styles.aboutLink}>Built with React + FastAPI</span>
              <span className={styles.aboutLink}>Hosted on Hetzner</span>
              <span className={styles.aboutLink}>Powered by Stalwart Mail Server</span>
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <SettingsLayout
      activeSection={activeSection}
      onSectionChange={setActiveSection}
    >
      {renderContent()}
    </SettingsLayout>
  );
}
