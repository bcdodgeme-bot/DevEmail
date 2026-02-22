import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search,
  Inbox,
  Users,
  Calendar,
  Settings,
  Send,
  Trash2,
  FileEdit,
  Star,
  Command,
} from 'lucide-react';
import { composeAPI } from '../../api/compose';
import styles from './CommandPalette.module.css';

const PAGES = [
  { id: 'inbox', label: 'Inbox', icon: Inbox, path: '/inbox' },
  { id: 'sent', label: 'Sent', icon: Send, path: '/inbox/sent' },
  { id: 'drafts', label: 'Drafts', icon: FileEdit, path: '/inbox/drafts' },
  { id: 'starred', label: 'Starred', icon: Star, path: '/inbox/starred' },
  { id: 'trash', label: 'Trash', icon: Trash2, path: '/inbox/trash' },
  { id: 'contacts', label: 'Contacts', icon: Users, path: '/contacts' },
  { id: 'calendar', label: 'Calendar', icon: Calendar, path: '/calendar' },
  { id: 'settings', label: 'Settings', icon: Settings, path: '/settings' },
];

const ACTIONS = [
  { id: 'compose', label: 'Compose new email', icon: Send, action: 'compose' },
];

/**
 * CommandPalette — Cmd+K omnibar.
 * isOpen, onClose, onCompose
 */
export default function CommandPalette({ isOpen, onClose, onCompose }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [contactResults, setContactResults] = useState([]);
  const inputRef = useRef(null);
  const navigate = useNavigate();
  const debounceRef = useRef(null);

  /* Focus on open */
  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setResults([]);
      setContactResults([]);
      setActiveIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  /* Filter results */
  useEffect(() => {
    const q = query.toLowerCase().trim();

    if (!q) {
      setResults([...PAGES, ...ACTIONS]);
      setContactResults([]);
      return;
    }

    const filteredPages = PAGES.filter((p) => p.label.toLowerCase().includes(q));
    const filteredActions = ACTIONS.filter((a) => a.label.toLowerCase().includes(q));
    setResults([...filteredPages, ...filteredActions]);
    setActiveIndex(0);

    /* Search contacts */
    clearTimeout(debounceRef.current);
    if (q.length >= 2) {
      debounceRef.current = setTimeout(async () => {
        try {
          const data = await composeAPI.searchContacts(q, 5);
          setContactResults(data.contacts || []);
        } catch {
          setContactResults([]);
        }
      }, 200);
    } else {
      setContactResults([]);
    }

    return () => clearTimeout(debounceRef.current);
  }, [query]);

  /* Compute total items */
  const totalItems = results.length + contactResults.length;

  /* Execute selection */
  const executeItem = useCallback(
    (index) => {
      if (index < results.length) {
        const item = results[index];
        if (item.path) {
          navigate(item.path);
          onClose();
        } else if (item.action === 'compose') {
          onCompose?.();
          onClose();
        }
      } else {
        const contactIdx = index - results.length;
        const contact = contactResults[contactIdx];
        if (contact) {
          navigate(`/contacts`);
          onClose();
        }
      }
    },
    [results, contactResults, navigate, onClose, onCompose]
  );

  /* Keyboard nav */
  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((prev) => Math.min(prev + 1, totalItems - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((prev) => Math.max(prev - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      executeItem(activeIndex);
    } else if (e.key === 'Escape') {
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.palette}>
        {/* Input */}
        <div className={styles.inputRow}>
          <Search size={16} className={styles.searchIcon} />
          <input
            ref={inputRef}
            className={styles.input}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search pages, contacts, or actions..."
          />
          <kbd className={styles.kbd}>ESC</kbd>
        </div>

        {/* Results */}
        <div className={styles.results}>
          {results.length > 0 && (
            <div className={styles.group}>
              <span className={styles.groupLabel}>
                {query ? 'Results' : 'Quick Navigation'}
              </span>
              {results.map((item, i) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    className={`${styles.resultItem} ${
                      i === activeIndex ? styles.resultActive : ''
                    }`}
                    onClick={() => executeItem(i)}
                    onMouseEnter={() => setActiveIndex(i)}
                    type="button"
                  >
                    <Icon size={16} className={styles.resultIcon} />
                    <span className={styles.resultLabel}>{item.label}</span>
                    {item.path && (
                      <span className={styles.resultHint}>{item.path}</span>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {contactResults.length > 0 && (
            <div className={styles.group}>
              <span className={styles.groupLabel}>Contacts</span>
              {contactResults.map((contact, i) => {
                const globalIdx = results.length + i;
                return (
                  <button
                    key={contact.id}
                    className={`${styles.resultItem} ${
                      globalIdx === activeIndex ? styles.resultActive : ''
                    }`}
                    onClick={() => executeItem(globalIdx)}
                    onMouseEnter={() => setActiveIndex(globalIdx)}
                    type="button"
                  >
                    <Users size={16} className={styles.resultIcon} />
                    <span className={styles.resultLabel}>
                      {contact.display_name ||
                        `${contact.first_name || ''} ${contact.last_name || ''}`.trim()}
                    </span>
                    <span className={styles.resultHint}>
                      {contact.emails?.[0]?.address || contact.company || ''}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {totalItems === 0 && query && (
            <div className={styles.noResults}>No results for "{query}"</div>
          )}
        </div>

        {/* Footer */}
        <div className={styles.footer}>
          <span className={styles.footerHint}>
            <kbd className={styles.kbdSmall}>↑</kbd>
            <kbd className={styles.kbdSmall}>↓</kbd> navigate
          </span>
          <span className={styles.footerHint}>
            <kbd className={styles.kbdSmall}>↵</kbd> select
          </span>
          <span className={styles.footerHint}>
            <kbd className={styles.kbdSmall}>esc</kbd> close
          </span>
        </div>
      </div>
    </div>
  );
}
