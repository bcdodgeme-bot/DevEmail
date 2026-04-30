import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import styles from './ContextMenu.module.css';

/**
 * Cursor-anchored context menu. Closes on outside click, Escape, or scroll.
 * Clamps within viewport bounds.
 *
 *   <ContextMenu
 *     anchor={{ x, y }}            // viewport coords; pass null to hide
 *     onClose={() => setMenu(null)}
 *     items={[
 *       { label: 'Move to Bulk', onClick: () => ... },
 *       { type: 'separator' },
 *       { label: 'Mark unread', onClick: () => ... },
 *     ]}
 *   />
 */
export default function ContextMenu({ anchor, items, onClose }) {
  const ref = useRef(null);
  const [pos, setPos] = useState({ x: 0, y: 0, ready: false });

  // Close on Escape, outside click, or any scroll.
  useEffect(() => {
    if (!anchor) return;

    const handleKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    const handleClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    };
    const handleScroll = () => onClose();

    window.addEventListener('keydown', handleKey);
    // capture phase: catch the click before any onClick on the menu fires
    document.addEventListener('mousedown', handleClick, true);
    window.addEventListener('scroll', handleScroll, true);

    return () => {
      window.removeEventListener('keydown', handleKey);
      document.removeEventListener('mousedown', handleClick, true);
      window.removeEventListener('scroll', handleScroll, true);
    };
  }, [anchor, onClose]);

  // After render, measure the menu and clamp into the viewport. We do
  // this in useLayoutEffect so the user never sees the unclamped flash.
  useLayoutEffect(() => {
    if (!anchor || !ref.current) {
      setPos({ x: 0, y: 0, ready: false });
      return;
    }
    const rect = ref.current.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const PAD = 6;

    let x = anchor.x;
    let y = anchor.y;
    if (x + rect.width + PAD > vw) x = Math.max(PAD, vw - rect.width - PAD);
    if (y + rect.height + PAD > vh) y = Math.max(PAD, vh - rect.height - PAD);
    setPos({ x, y, ready: true });
  }, [anchor]);

  if (!anchor) return null;

  return (
    <div
      ref={ref}
      role="menu"
      className={styles.menu}
      style={{
        left: pos.x,
        top: pos.y,
        visibility: pos.ready ? 'visible' : 'hidden',
      }}
    >
      {items.map((item, idx) => {
        if (item.type === 'separator') {
          return <div key={`sep-${idx}`} className={styles.separator} role="separator" />;
        }
        return (
          <button
            key={item.label}
            type="button"
            role="menuitem"
            className={styles.item}
            disabled={item.disabled}
            onClick={() => {
              onClose();
              item.onClick?.();
            }}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
