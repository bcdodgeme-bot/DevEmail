import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { Search, X, Filter, Mail, Paperclip, Calendar } from 'lucide-react';
import { selectAccounts } from '../../store/accountsSlice';
import { apiFetch } from '../../utils/api';
import { formatDate } from '../../utils/formatDate';
import styles from './SearchModal.module.css';

export default function SearchModal({ isOpen, onClose }) {
  const navigate = useNavigate();
  const accounts = useSelector(selectAccounts);

  const [query, setQuery] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState({
    account_id: '',
    date_from: '',
    date_to: '',
    has_attachment: false,
    is_read: '',
  });
  const [results, setResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [total, setTotal] = useState(0);

  const inputRef = useRef(null);
  const debounceRef = useRef(null);

  /* Focus on open */
  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setResults([]);
      setTotal(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  /* Debounced search */
  const doSearch = useCallback(async (q, f) => {
    if (!q.trim() && !f.account_id && !f.date_from) {
      setResults([]);
      setTotal(0);
      return;
    }

    setIsSearching(true);
    try {
      const params = new URLSearchParams();
      if (q.trim()) params.set('search', q.trim());
      if (f.account_id) params.set('account_id', f.account_id);
      if (f.date_from) params.set('date_from', f.date_from);
      if (f.date_to) params.set('date_to', f.date_to);
      if (f.has_attachment) params.set('has_attachment', 'true');
      if (f.is_read === 'true' || f.is_read === 'false') params.set('is_read', f.is_read);
      params.set('per_page', '20');

      const data = await apiFetch(`/messages/search?${params}`);
      setResults(data.messages || data.threads || []);
      setTotal(data.total || 0);
    } catch {
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  }, []);

  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(query, filters), 300);
    return () => clearTimeout(debounceRef.current);
  }, [query, filters, doSearch]);

  /* Select a result */
  const handleSelectResult = (result) => {
    const threadId = result.thread_id || result.id;
    navigate(`/inbox/${threadId}`);
    onClose();
  };

  const updateFilter = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  if (!isOpen) return null;

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        {/* Input */}
        <div className={styles.inputRow}>
          <Search size={16} className={styles.searchIcon} />
          <input
            ref={inputRef}
            className={styles.input}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && onClose()}
            placeholder="Search emails..."
          />
          <button
            className={`${styles.filterToggle} ${showFilters ? styles.filterToggleActive : ''}`}
            onClick={() => setShowFilters(!showFilters)}
            title="Filters"
            type="button"
          >
            <Filter size={14} />
          </button>
          <button className={styles.closeBtn} onClick={onClose} type="button">
            <X size={16} />
          </button>
        </div>

        {/* Filters */}
        {showFilters && (
          <div className={styles.filters}>
            <div className={styles.filterRow}>
              <div className={styles.filterField}>
                <label className={styles.filterLabel}>Account</label>
                <select
                  className={styles.filterSelect}
                  value={filters.account_id}
                  onChange={(e) => updateFilter('account_id', e.target.value)}
                >
                  <option value="">All accounts</option>
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>{a.email_address}</option>
                  ))}
                </select>
              </div>
              <div className={styles.filterField}>
                <label className={styles.filterLabel}>Read status</label>
                <select
                  className={styles.filterSelect}
                  value={filters.is_read}
                  onChange={(e) => updateFilter('is_read', e.target.value)}
                >
                  <option value="">Any</option>
                  <option value="true">Read</option>
                  <option value="false">Unread</option>
                </select>
              </div>
            </div>
            <div className={styles.filterRow}>
              <div className={styles.filterField}>
                <label className={styles.filterLabel}>From date</label>
                <input
                  className={styles.filterInput}
                  type="date"
                  value={filters.date_from}
                  onChange={(e) => updateFilter('date_from', e.target.value)}
                />
              </div>
              <div className={styles.filterField}>
                <label className={styles.filterLabel}>To date</label>
                <input
                  className={styles.filterInput}
                  type="date"
                  value={filters.date_to}
                  onChange={(e) => updateFilter('date_to', e.target.value)}
                />
              </div>
              <label className={styles.checkLabel}>
                <input
                  type="checkbox"
                  checked={filters.has_attachment}
                  onChange={(e) => updateFilter('has_attachment', e.target.checked)}
                  className={styles.checkbox}
                />
                <Paperclip size={12} /> Has attachment
              </label>
            </div>
          </div>
        )}

        {/* Results */}
        <div className={styles.results}>
          {isSearching && (
            <div className={styles.status}>Searching...</div>
          )}

          {!isSearching && results.length === 0 && query && (
            <div className={styles.status}>No results found</div>
          )}

          {!isSearching && !query && results.length === 0 && (
            <div className={styles.status}>Type to search your emails</div>
          )}

          {results.map((result) => (
            <button
              key={result.id}
              className={styles.resultItem}
              onClick={() => handleSelectResult(result)}
              type="button"
            >
              <Mail size={14} className={styles.resultIcon} />
              <div className={styles.resultInfo}>
                <span className={styles.resultSubject}>
                  {result.subject || '(no subject)'}
                </span>
                <span className={styles.resultMeta}>
                  {result.from_name || result.from_address || ''}
                  {result.received_at && ` · ${formatDate(result.received_at)}`}
                </span>
                {result.snippet && (
                  <span className={styles.resultSnippet}>{result.snippet}</span>
                )}
              </div>
            </button>
          ))}

          {total > results.length && (
            <div className={styles.moreCount}>
              Showing {results.length} of {total} results
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
