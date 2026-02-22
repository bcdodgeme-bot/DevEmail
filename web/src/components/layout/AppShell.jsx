import { useState, useEffect, useCallback } from 'react';
import { Outlet } from 'react-router-dom';
import NavRail from './NavRail';
import StatusBar from './StatusBar';
import ComposeModal from './compose/ComposeModal';
import CommandPalette from './common/CommandPalette';
import SearchModal from './common/SearchModal';
import styles from './AppShell.module.css';

export default function AppShell() {
  const [isComposing, setIsComposing] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isPaletteOpen, setIsPaletteOpen] = useState(false);
  const [composeProps, setComposeProps] = useState({});

  const handleCompose = useCallback(() => {
    setComposeProps({});
    setIsComposing(true);
  }, []);

  const handleSearch = useCallback(() => {
    setIsSearchOpen(true);
  }, []);

  /* Cmd+K → Command Palette */
  useEffect(() => {
    function handleKey(e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsPaletteOpen((prev) => !prev);
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, []);

  /* Listen for compose events from Contacts page */
  useEffect(() => {
    function handleComposeEvent(e) {
      const { to, replyTo, replyAll, forward } = e.detail || {};
      setComposeProps({ replyTo, replyAll, forward });
      if (to) {
        setComposeProps((prev) => ({ ...prev, prefillTo: to }));
      }
      setIsComposing(true);
    }
    window.addEventListener('devemail:compose', handleComposeEvent);
    return () => window.removeEventListener('devemail:compose', handleComposeEvent);
  }, []);

  return (
    <div className={styles.shell}>
      <div className={styles.main}>
        <NavRail
          unreadCount={0}
          onCompose={handleCompose}
          onSearch={handleSearch}
        />

        <div className={styles.content}>
          <Outlet />
        </div>
      </div>

      <StatusBar
        isConnected={true}
        isSyncing={false}
        lastSynced={null}
        accountCount={0}
      />

      {/* Background grid texture */}
      <div className={styles.gridOverlay} aria-hidden="true" />

      {/* Compose Modal */}
      <ComposeModal
        isOpen={isComposing}
        onClose={() => setIsComposing(false)}
        {...composeProps}
      />

      {/* Command Palette (Cmd+K) */}
      <CommandPalette
        isOpen={isPaletteOpen}
        onClose={() => setIsPaletteOpen(false)}
        onCompose={handleCompose}
      />

      {/* Search Modal */}
      <SearchModal
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
      />
    </div>
  );
}
