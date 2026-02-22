import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check } from 'lucide-react';
import { getInitials, getAvatarGradient } from '../../utils/avatarColor';
import styles from './AccountPicker.module.css';

export default function AccountPicker({ accounts, selectedId, onChange }) {
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef(null);

  const selected = accounts.find((a) => a.id === selectedId) || accounts[0];

  /* Close on outside click */
  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) {
        setIsOpen(false);
      }
    }
    if (isOpen) document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [isOpen]);

  if (!selected) return null;

  return (
    <div className={styles.picker} ref={ref}>
      <button
        className={styles.trigger}
        onClick={() => setIsOpen(!isOpen)}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <span className={styles.label}>From</span>
        <span
          className={styles.avatar}
          style={{ background: getAvatarGradient(selected.email_address) }}
        >
          {getInitials(selected.display_name || selected.email_address)}
        </span>
        <span className={styles.info}>
          <span className={styles.name}>
            {selected.display_name || selected.email_address}
          </span>
          <span className={styles.email}>{selected.email_address}</span>
        </span>
        <ChevronDown
          size={14}
          className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ''}`}
        />
      </button>

      {isOpen && accounts.length > 1 && (
        <div className={styles.dropdown} role="listbox">
          {accounts.map((account) => (
            <button
              key={account.id}
              className={`${styles.option} ${
                account.id === selectedId ? styles.optionActive : ''
              }`}
              onClick={() => {
                onChange(account.id);
                setIsOpen(false);
              }}
              role="option"
              aria-selected={account.id === selectedId}
              type="button"
            >
              <span
                className={styles.avatar}
                style={{ background: getAvatarGradient(account.email_address) }}
              >
                {getInitials(account.display_name || account.email_address)}
              </span>
              <span className={styles.info}>
                <span className={styles.name}>
                  {account.display_name || account.email_address}
                </span>
                <span className={styles.email}>{account.email_address}</span>
              </span>
              <span className={styles.provider}>{account.provider}</span>
              {account.id === selectedId && (
                <Check size={14} className={styles.check} />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
