import { useRef, useCallback } from 'react';
import { Search, UserPlus, Star } from 'lucide-react';
import ContactListItem from './ContactListItem';
import styles from './ContactList.module.css';

const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ#'.split('');

export default function ContactList({
  contacts,
  total,
  status,
  search,
  selectedId,
  onSearchChange,
  onSelect,
  onToggleFavorite,
  onAddNew,
  onLoadMore,
  hasMore,
}) {
  const listRef = useRef(null);

  /* Scroll to letter group */
  const scrollToLetter = useCallback(
    (letter) => {
      if (!listRef.current) return;
      const items = listRef.current.querySelectorAll('[data-letter]');
      for (const item of items) {
        if (item.dataset.letter === letter) {
          item.scrollIntoView({ behavior: 'smooth', block: 'start' });
          break;
        }
      }
    },
    []
  );

  /* Group contacts by first letter */
  const getFirstLetter = (contact) => {
    const name =
      contact.display_name ||
      contact.last_name ||
      contact.first_name ||
      contact.emails?.[0]?.address ||
      '?';
    const first = name.charAt(0).toUpperCase();
    return /[A-Z]/.test(first) ? first : '#';
  };

  /* Track which letters we've rendered headers for */
  let lastLetter = '';

  return (
    <div className={styles.container}>
      {/* Search bar */}
      <div className={styles.searchBar}>
        <div className={styles.searchField}>
          <Search size={14} className={styles.searchIcon} />
          <input
            className={styles.searchInput}
            type="text"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={`Search ${total.toLocaleString()} contacts...`}
          />
        </div>
        <button
          className={styles.addButton}
          onClick={onAddNew}
          title="Add contact"
          type="button"
        >
          <UserPlus size={16} />
        </button>
      </div>

      {/* Contact list */}
      <div className={styles.listWrapper}>
        <div className={styles.list} ref={listRef}>
          {status === 'loading' && contacts.length === 0 && (
            <div className={styles.loading}>Loading contacts...</div>
          )}

          {status === 'succeeded' && contacts.length === 0 && (
            <div className={styles.empty}>
              {search ? `No contacts matching "${search}"` : 'No contacts yet'}
            </div>
          )}

          {contacts.map((contact) => {
            const letter = getFirstLetter(contact);
            const showHeader = letter !== lastLetter;
            if (showHeader) lastLetter = letter;

            return (
              <div key={contact.id}>
                {showHeader && (
                  <div className={styles.letterHeader} data-letter={letter}>
                    {letter}
                  </div>
                )}
                <ContactListItem
                  contact={contact}
                  isSelected={contact.id === selectedId}
                  onSelect={onSelect}
                  onToggleFavorite={onToggleFavorite}
                />
              </div>
            );
          })}

          {hasMore && (
            <button
              className={styles.loadMore}
              onClick={onLoadMore}
              type="button"
            >
              Load more...
            </button>
          )}
        </div>

        {/* Alphabet sidebar */}
        <div className={styles.alphabet}>
          {ALPHABET.map((letter) => (
            <button
              key={letter}
              className={styles.alphaLetter}
              onClick={() => scrollToLetter(letter)}
              type="button"
              title={letter}
            >
              {letter}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
