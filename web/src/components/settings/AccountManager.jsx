import { useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import {
  Mail,
  Plus,
  Trash2,
  RefreshCw,
  ExternalLink,
  Check,
  Server,
} from 'lucide-react';
import {
  selectAccounts,
  fetchAccounts,
  linkStalwart,
  updateAccount,
  unlinkAccount,
} from '../../store/accountsSlice';
import { getInitials, getAvatarGradient } from '../../utils/avatarColor';
import { apiFetch } from '../../utils/api';
import styles from './AccountManager.module.css';

export default function AccountManager() {
  const dispatch = useDispatch();
  const accounts = useSelector(selectAccounts);

  const [showStalwartForm, setShowStalwartForm] = useState(false);
  const [stalwartForm, setStalwartForm] = useState({
    email_address: '',
    display_name: '',
    username: '',
    password: '',
    imap_host: 'mail.damnitcarl.dev',
    imap_port: 993,
    smtp_host: 'mail.damnitcarl.dev',
    smtp_port: 465,
  });
  const [isLinking, setIsLinking] = useState(false);
  const [error, setError] = useState(null);

  /* Link Gmail via OAuth — authenticated API call, then redirect to Google */
  const handleLinkGmail = async () => {
    try {
      setError(null);
      const { auth_url } = await apiFetch('/auth/google/login');
      window.location.href = auth_url;
    } catch (err) {
      setError(err.message || 'Failed to start Google OAuth');
    }
  };

  /* Link Stalwart account */
  const handleLinkStalwart = async () => {
    if (!stalwartForm.email_address || !stalwartForm.username || !stalwartForm.password) {
      setError('Email, username, and password are required');
      return;
    }
    setIsLinking(true);
    setError(null);
    try {
      await dispatch(linkStalwart(stalwartForm)).unwrap();
      setShowStalwartForm(false);
      setStalwartForm({
        email_address: '',
        display_name: '',
        username: '',
        password: '',
        imap_host: 'mail.damnitcarl.dev',
        imap_port: 993,
        smtp_host: 'mail.damnitcarl.dev',
        smtp_port: 465,
      });
    } catch (err) {
      setError(err.message || 'Failed to link account');
    } finally {
      setIsLinking(false);
    }
  };

  /* Toggle sync */
  const handleToggleSync = (account) => {
    dispatch(
      updateAccount({
        accountId: account.id,
        data: { sync_enabled: !account.sync_enabled },
      })
    );
  };

  /* Set as default */
  const handleSetDefault = (account) => {
    dispatch(
      updateAccount({
        accountId: account.id,
        data: { is_default: true },
      })
    );
  };

  /* Unlink */
  const handleUnlink = (account) => {
    if (window.confirm(`Unlink ${account.email_address}? This will stop syncing from this account. Your existing emails will be kept.`)) {
      dispatch(unlinkAccount(account.id));
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h3 className={styles.title}>Email Accounts</h3>
        <p className={styles.subtitle}>
          Link email accounts to send and receive from DevEmail
        </p>
      </div>

      {/* Error display */}
      {error && <div className={styles.formError}>{error}</div>}

      {/* Existing accounts */}
      <div className={styles.accountList}>
        {accounts.map((account) => (
          <div key={account.id} className={styles.accountCard}>
            <div className={styles.accountMain}>
              <span
                className={styles.avatar}
                style={{ background: getAvatarGradient(account.email_address) }}
              >
                {getInitials(account.display_name || account.email_address)}
              </span>
              <div className={styles.accountInfo}>
                <span className={styles.accountName}>
                  {account.display_name || account.email_address}
                </span>
                <span className={styles.accountEmail}>{account.email_address}</span>
                <div className={styles.accountMeta}>
                  <span className={styles.providerBadge}>{account.provider}</span>
                  {account.is_default && (
                    <span className={styles.defaultBadge}>Default</span>
                  )}
                  <span className={account.sync_enabled ? styles.syncOn : styles.syncOff}>
                    {account.sync_enabled ? 'Syncing' : 'Paused'}
                  </span>
                </div>
              </div>
            </div>
            <div className={styles.accountActions}>
              {!account.is_default && (
                <button
                  className={styles.actionBtn}
                  onClick={() => handleSetDefault(account)}
                  title="Set as default"
                  type="button"
                >
                  <Check size={14} />
                </button>
              )}
              <button
                className={styles.actionBtn}
                onClick={() => handleToggleSync(account)}
                title={account.sync_enabled ? 'Pause sync' : 'Enable sync'}
                type="button"
              >
                <RefreshCw size={14} />
              </button>
              <button
                className={`${styles.actionBtn} ${styles.deleteBtn}`}
                onClick={() => handleUnlink(account)}
                title="Unlink account"
                type="button"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))}

        {accounts.length === 0 && (
          <div className={styles.empty}>No email accounts linked yet</div>
        )}
      </div>

      {/* Add account buttons */}
      <div className={styles.addSection}>
        <button className={styles.addGmailBtn} onClick={handleLinkGmail} type="button">
          <Mail size={16} />
          Link Gmail Account
          <ExternalLink size={12} />
        </button>
        <button
          className={styles.addStalwartBtn}
          onClick={() => setShowStalwartForm(!showStalwartForm)}
          type="button"
        >
          <Server size={16} />
          {showStalwartForm ? 'Cancel' : 'Link Stalwart Account'}
        </button>
      </div>

      {/* Stalwart form */}
      {showStalwartForm && (
        <div className={styles.stalwartForm}>
          <div className={styles.formRow}>
            <div className={styles.formField}>
              <label className={styles.formLabel}>Email Address</label>
              <input
                className={styles.formInput}
                type="email"
                value={stalwartForm.email_address}
                onChange={(e) =>
                  setStalwartForm({ ...stalwartForm, email_address: e.target.value })
                }
                placeholder="you@mail.damnitcarl.dev"
              />
            </div>
            <div className={styles.formField}>
              <label className={styles.formLabel}>Display Name</label>
              <input
                className={styles.formInput}
                type="text"
                value={stalwartForm.display_name}
                onChange={(e) =>
                  setStalwartForm({ ...stalwartForm, display_name: e.target.value })
                }
                placeholder="Your Name"
              />
            </div>
          </div>
          <div className={styles.formRow}>
            <div className={styles.formField}>
              <label className={styles.formLabel}>Username</label>
              <input
                className={styles.formInput}
                type="text"
                value={stalwartForm.username}
                onChange={(e) =>
                  setStalwartForm({ ...stalwartForm, username: e.target.value })
                }
                placeholder="bcdodgeme"
              />
            </div>
            <div className={styles.formField}>
              <label className={styles.formLabel}>Password</label>
              <input
                className={styles.formInput}
                type="password"
                value={stalwartForm.password}
                onChange={(e) =>
                  setStalwartForm({ ...stalwartForm, password: e.target.value })
                }
                placeholder="••••••••"
              />
            </div>
          </div>
          <div className={styles.formRow}>
            <div className={styles.formField}>
              <label className={styles.formLabel}>IMAP Host</label>
              <input
                className={styles.formInput}
                type="text"
                value={stalwartForm.imap_host}
                onChange={(e) =>
                  setStalwartForm({ ...stalwartForm, imap_host: e.target.value })
                }
              />
            </div>
            <div className={styles.formField}>
              <label className={styles.formLabel}>SMTP Host</label>
              <input
                className={styles.formInput}
                type="text"
                value={stalwartForm.smtp_host}
                onChange={(e) =>
                  setStalwartForm({ ...stalwartForm, smtp_host: e.target.value })
                }
              />
            </div>
          </div>

          {error && <div className={styles.formError}>{error}</div>}

          <button
            className={styles.linkBtn}
            onClick={handleLinkStalwart}
            disabled={isLinking}
            type="button"
          >
            {isLinking ? 'Linking...' : 'Link Account'}
          </button>
        </div>
      )}
    </div>
  );
}
