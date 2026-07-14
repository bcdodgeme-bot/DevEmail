import { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { NavLink, useLocation } from 'react-router-dom';
import {
  Mail,
  Send,
  FileEdit,
  Trash2,
  ShieldAlert,
  Folder as FolderIcon,
  Users,
  Calendar,
  Search,
  Settings,
  LogOut,
  PenSquare,
} from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { fetchFolders, selectCustomFolders } from '../../store/foldersSlice';
import { getInitials, getAvatarGradient } from '../../utils/avatarColor';
import { ROUTES } from '../../utils/constants';
import styles from './NavRail.module.css';

const NAV_ITEMS = [
  { path: ROUTES.INBOX, icon: Mail, label: 'Inbox', badge: true },
  { path: ROUTES.SENT, icon: Send, label: 'Sent' },
  { path: ROUTES.DRAFTS, icon: FileEdit, label: 'Drafts' },
  { path: ROUTES.SPAM, icon: ShieldAlert, label: 'Junk' },
  { path: ROUTES.TRASH, icon: Trash2, label: 'Trash' },
];

const SECONDARY_ITEMS = [
  { path: ROUTES.CONTACTS, icon: Users, label: 'Contacts' },
  { path: ROUTES.CALENDAR, icon: Calendar, label: 'Calendar' },
];

export default function NavRail({ unreadCount = 0, onCompose, onSearch }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const dispatch = useDispatch();
  const customFolders = useSelector(selectCustomFolders);

  useEffect(() => {
    dispatch(fetchFolders());
  }, [dispatch]);

  return (
    <nav className={styles.rail} aria-label="Main navigation">
      {/* Logo */}
      <div className={styles.logo}>
        <img
          src="/logo.png"
          alt="DevEmail"
          className={styles.logoImage}
          width="36"
          height="36"
        />
      </div>

      {/* Compose button */}
      <button
        className={styles.composeButton}
        onClick={onCompose}
        title="Compose (c)"
        aria-label="Compose new email"
      >
        <PenSquare size={20} />
      </button>

      {/* Scrollable middle — grows to fill and scrolls when there are many
          folders, so the pinned bottom actions stay reachable. */}
      <div className={styles.scrollArea}>
      {/* Primary nav */}
      <div className={styles.section}>
        {NAV_ITEMS.map(({ path, icon: Icon, label, badge }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.active : ''}`
            }
            title={label}
            aria-label={label}
          >
            <Icon size={20} strokeWidth={1.75} />
            {badge && unreadCount > 0 && (
              <span className={styles.badge}>
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </NavLink>
        ))}
      </div>

      {/* Custom (server-synced) folders */}
      {customFolders.length > 0 && (
        <div className={styles.section}>
          {customFolders.map((f) => (
            <NavLink
              key={f.id}
              to={`/folder/${f.id}`}
              className={({ isActive }) =>
                `${styles.navItem} ${isActive ? styles.active : ''}`
              }
              title={f.name}
              aria-label={f.name}
            >
              <FolderIcon size={20} strokeWidth={1.75} />
            </NavLink>
          ))}
        </div>
      )}

      {/* Divider */}
      <div className={styles.divider} />

      {/* Secondary nav */}
      <div className={styles.section}>
        {SECONDARY_ITEMS.map(({ path, icon: Icon, label }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.active : ''}`
            }
            title={label}
            aria-label={label}
          >
            <Icon size={20} strokeWidth={1.75} />
          </NavLink>
        ))}
      </div>
      </div>{/* /scrollArea */}

      {/* Bottom actions (pinned) */}
      <div className={`${styles.section} ${styles.bottom}`}>
        <button
          className={styles.navItem}
          onClick={onSearch}
          title="Search (⌘K)"
          aria-label="Search"
        >
          <Search size={20} strokeWidth={1.75} />
        </button>

        <NavLink
          to={ROUTES.SETTINGS}
          className={({ isActive }) =>
            `${styles.navItem} ${isActive ? styles.active : ''}`
          }
          title="Settings"
          aria-label="Settings"
        >
          <Settings size={20} strokeWidth={1.75} />
        </NavLink>

        {/* User avatar / logout */}
        <button
          className={styles.userAvatar}
          onClick={logout}
          title={`${user?.display_name || user?.email || 'User'} — Click to sign out`}
          aria-label="Sign out"
        >
          {user?.avatar_url ? (
            <img
              src={user.avatar_url}
              alt={user.display_name}
              className={styles.avatarImage}
            />
          ) : (
            <span
              className={styles.avatarInitials}
              style={{ background: getAvatarGradient(user?.display_name || user?.email) }}
            >
              {getInitials(user?.display_name || user?.email)}
            </span>
          )}
        </button>
      </div>
    </nav>
  );
}
