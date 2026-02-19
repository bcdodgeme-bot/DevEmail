import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import NavRail from './NavRail';
import StatusBar from './StatusBar';
import styles from './AppShell.module.css';

export default function AppShell() {
  const [isComposing, setIsComposing] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);

  const handleCompose = () => {
    setIsComposing(true);
    // ComposeModal will be built in Phase 3
  };

  const handleSearch = () => {
    setIsSearchOpen(true);
    // CommandPalette will be built in Phase 6
  };

  return (
    <div className={styles.shell}>
      <div className={styles.main}>
        <NavRail
          unreadCount={0}
          onCompose={handleCompose}
          onSearch={handleSearch}
        />

        <div className={styles.content}>
          {/* Outlet renders the active route's component */}
          {/* Each route provides its own center + right panel layout */}
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
    </div>
  );
}
