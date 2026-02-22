import { useState, useRef, useEffect, useCallback } from 'react';
import { X } from 'lucide-react';
import { getInitials, getAvatarGradient } from '../../utils/avatarColor';
import { composeAPI } from '../../api/compose';
import styles from './RecipientInput.module.css';

/**
 * Tag-style email input with contact autocomplete.
 * value = [{ address: "foo@bar.com", name: "Foo" }, ...]
 * onChange = (newValue) => void
 */
export default function RecipientInput({ label, value = [], onChange, placeholder }) {
  const [inputValue, setInputValue] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [isFocused, setIsFocused] = useState(false);
  const inputRef = useRef(null);
  const containerRef = useRef(null);
  const debounceRef = useRef(null);

  /* Search contacts as user types */
  const searchContacts = useCallback(async (query) => {
    if (query.length < 2) {
      setSuggestions([]);
      return;
    }
    try {
      const result = await composeAPI.searchContacts(query);
      const contacts = (result.contacts || []).filter((c) => {
        /* Exclude contacts already added */
        const existingAddresses = value.map((v) => v.address.toLowerCase());
        return c.emails?.some(
          (e) => !existingAddresses.includes(e.address.toLowerCase())
        );
      });
      setSuggestions(contacts);
      setActiveIndex(-1);
    } catch {
      setSuggestions([]);
    }
  }, [value]);

  useEffect(() => {
    clearTimeout(debounceRef.current);
    if (inputValue.trim()) {
      debounceRef.current = setTimeout(() => searchContacts(inputValue.trim()), 250);
    } else {
      setSuggestions([]);
    }
    return () => clearTimeout(debounceRef.current);
  }, [inputValue, searchContacts]);

  /* Close suggestions on outside click */
  useEffect(() => {
    function handleClick(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setSuggestions([]);
        setIsFocused(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  /* Add a recipient */
  const addRecipient = (address, name = null) => {
    const trimmed = address.trim();
    if (!trimmed) return;
    /* Avoid duplicates */
    if (value.some((r) => r.address.toLowerCase() === trimmed.toLowerCase())) return;
    onChange([...value, { address: trimmed, name }]);
    setInputValue('');
    setSuggestions([]);
    setActiveIndex(-1);
  };

  /* Select a contact from suggestions */
  const selectContact = (contact) => {
    const email = contact.emails?.[0];
    if (email) {
      addRecipient(email.address, contact.display_name || contact.first_name);
    }
  };

  /* Remove a recipient */
  const removeRecipient = (index) => {
    const next = [...value];
    next.splice(index, 1);
    onChange(next);
  };

  /* Handle keyboard navigation */
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === 'Tab' || e.key === ',') {
      e.preventDefault();
      if (activeIndex >= 0 && suggestions[activeIndex]) {
        selectContact(suggestions[activeIndex]);
      } else if (inputValue.includes('@')) {
        addRecipient(inputValue);
      }
    } else if (e.key === 'Backspace' && !inputValue && value.length > 0) {
      removeRecipient(value.length - 1);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((prev) => Math.min(prev + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((prev) => Math.max(prev - 1, -1));
    } else if (e.key === 'Escape') {
      setSuggestions([]);
      setActiveIndex(-1);
    }
  };

  return (
    <div className={styles.wrapper} ref={containerRef}>
      <span className={styles.label}>{label}</span>
      <div
        className={`${styles.field} ${isFocused ? styles.fieldFocused : ''}`}
        onClick={() => inputRef.current?.focus()}
      >
        {value.map((recipient, i) => (
          <span key={`${recipient.address}-${i}`} className={styles.tag}>
            <span className={styles.tagText}>
              {recipient.name || recipient.address}
            </span>
            <button
              className={styles.tagRemove}
              onClick={(e) => {
                e.stopPropagation();
                removeRecipient(i);
              }}
              type="button"
              aria-label={`Remove ${recipient.address}`}
            >
              <X size={12} />
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          className={styles.input}
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setIsFocused(true)}
          onBlur={() => {
            /* Delay to allow click on suggestion */
            setTimeout(() => setIsFocused(false), 200);
          }}
          placeholder={value.length === 0 ? placeholder : ''}
          aria-label={label}
        />
      </div>

      {/* Autocomplete suggestions */}
      {suggestions.length > 0 && (
        <div className={styles.suggestions} role="listbox">
          {suggestions.map((contact, i) => (
            <button
              key={contact.id}
              className={`${styles.suggestion} ${
                i === activeIndex ? styles.suggestionActive : ''
              }`}
              onClick={() => selectContact(contact)}
              role="option"
              aria-selected={i === activeIndex}
              type="button"
            >
              <span
                className={styles.sugAvatar}
                style={{
                  background: getAvatarGradient(
                    contact.display_name || contact.emails?.[0]?.address || '?'
                  ),
                }}
              >
                {getInitials(contact.display_name || contact.emails?.[0]?.address)}
              </span>
              <span className={styles.sugInfo}>
                <span className={styles.sugName}>
                  {contact.display_name || `${contact.first_name || ''} ${contact.last_name || ''}`.trim()}
                </span>
                <span className={styles.sugEmail}>
                  {contact.emails?.[0]?.address}
                </span>
                {contact.company && (
                  <span className={styles.sugCompany}>{contact.company}</span>
                )}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
