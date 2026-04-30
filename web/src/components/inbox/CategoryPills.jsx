import { useMemo } from 'react';
import styles from './CategoryPills.module.css';

/**
 * Three-button pill row above the inbox list: All · People · Bulk.
 * Active state = `activeCategory` (null/'all' means All).
 * Counts come from /messages/category-counts (fetched into Redux by the
 * containing page).
 */
export default function CategoryPills({
  activeCategory,        // null | 'all' | 'people' | 'bulk'
  counts,                // { all: {unread, total}, people: {...}, bulk: {...} }
  onChange,              // (category) => void;  category is 'all' | 'people' | 'bulk'
}) {
  const pills = useMemo(() => ([
    { key: 'all',    label: 'All' },
    { key: 'people', label: 'People' },
    { key: 'bulk',   label: 'Bulk' },
  ]), []);

  const normalizedActive = activeCategory || 'all';

  return (
    <div
      className={styles.pillRow}
      role="tablist"
      aria-label="Filter messages by category"
    >
      {pills.map(({ key, label }) => {
        const slot = counts?.[key] || { unread: 0, total: 0 };
        const isActive = normalizedActive === key;
        const isZero = slot.unread === 0;

        return (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={isActive}
            className={[
              styles.pill,
              isActive ? styles.active : '',
            ].filter(Boolean).join(' ')}
            onClick={() => onChange(key)}
            title={`${slot.unread} unread · ${slot.total} total`}
          >
            <span className={styles.label}>{label}</span>
            <span
              className={[styles.count, isZero ? styles.countZero : ''].filter(Boolean).join(' ')}
              data-testid={`pill-count-${key}`}
            >
              {slot.unread}
            </span>
          </button>
        );
      })}
    </div>
  );
}
