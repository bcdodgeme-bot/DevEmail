import { useState, useEffect, useCallback } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { Outlet } from 'react-router-dom';
import NavRail from './NavRail';
import StatusBar from './StatusBar';
import ComposeModal from '../compose/ComposeModal';
import CommandPalette from '../common/CommandPalette';
import SearchModal from '../common/SearchModal';
import { fetchAccounts, selectAccounts } from '../../store/accountsSlice';
import {
  fetchThreads,
  selectListStatus,
  selectUnreadCount,
  selectLastSynced,
  selectIsConnected,
} from '../../store/inboxSlice';
import styles from './AppShell.module.css';

export default function AppShell() {
  const dispatch = useDispatch();

  const [isComposing, setIsComposing] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isPaletteOpen, setIsPaletteOpen] = useState(false);
  const [composeProps, setComposeProps] = useState({});

  // Live data from Redux
  const accounts = useSelector(selectAccounts);
  const unreadCount = useSelector(selectUnreadCount);
  const listStatus = useSelector(selectListStatus);
  const lastSynced = useSelector(selectLastSynced);
  const isConnected = useSelector(selectIsConnected);

  // Fetch accounts and inbox threads on mount
  useEffect(() => {
    dispatch(fetchAccounts());
    dispatch(fetchThreads({ view: 'inbox' }));
  }, [dispatch]);

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
          unreadCount={unreadCount}
          onCompose={handleCompose}
          onSearch={handleSearch}
        />

        <div className={styles.content}>
          <Outlet />
        </div>
      </div>

      <StatusBar
        isConnected={isConnected}
        isSyncing={listStatus === 'loading'}
        lastSynced={lastSynced}
        accountCount={accounts.length}
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
