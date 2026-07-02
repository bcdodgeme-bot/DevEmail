import { useEffect, useState, useCallback } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useLocation, useParams, useSearchParams } from 'react-router-dom';
import { PenSquare } from 'lucide-react';
import {
  fetchThreads,
  fetchThreadDetail,
  markRead,
  setView,
  setCategory,
  selectThread,
  selectThreads,
  selectListStatus,
  selectSelectedThreadId,
  selectThreadDetail,
  selectDetailStatus,
  selectView,
  selectCategoryFilter,
  setMessageCategory,
} from '../store/inboxSlice';
import {
  fetchCategoryCounts,
  selectCategoryCounts,
} from '../store/categorySlice';
import { showToast } from '../store/toastSlice';
import { selectFolders } from '../store/foldersSlice';
import ThreadList from '../components/inbox/ThreadList';
import ThreadDetail from '../components/inbox/ThreadDetail';
import EmptyState from '../components/inbox/EmptyState';
import CategoryPills from '../components/inbox/CategoryPills';
import ContextMenu from '../components/inbox/ContextMenu';
import MoveCategoryModal from '../components/inbox/MoveCategoryModal';
import styles from './Inbox.module.css';

/** Map route pathname → API view name */
function viewFromPath(pathname) {
  if (pathname.startsWith('/sent')) return 'sent';
  if (pathname.startsWith('/drafts')) return 'drafts';
  if (pathname.startsWith('/trash')) return 'trash';
  if (pathname.startsWith('/spam')) return 'spam';
  // Custom folder view: the API view name IS "folder/<id>", so
  // fetchThreads hits GET /messages/folder/<id> directly.
  if (pathname.startsWith('/folder/')) return pathname.slice(1);
  return 'inbox';
}

const VIEW_LABELS = {
  inbox: 'Inbox',
  sent: 'Sent',
  drafts: 'Drafts',
  trash: 'Trash',
  spam: 'Junk',
};

/** Normalize ?category= URL value to one of: 'all' | 'people' | 'bulk'. */
function normalizeCategoryParam(raw) {
  if (raw === 'people' || raw === 'bulk') return raw;
  return 'all';
}

export default function Inbox() {
  const dispatch = useDispatch();
  const location = useLocation();
  const { threadId: urlThreadId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();

  const threads = useSelector(selectThreads);
  const listStatus = useSelector(selectListStatus);
  const selectedId = useSelector(selectSelectedThreadId);
  const threadDetail = useSelector(selectThreadDetail);
  const detailStatus = useSelector(selectDetailStatus);
  const currentView = useSelector(selectView);
  const folders = useSelector(selectFolders);
  const sliceCategory = useSelector(selectCategoryFilter);
  const counts = useSelector(selectCategoryCounts);

  const urlCategory = normalizeCategoryParam(searchParams.get('category'));

  /* Local UI state for the context menu + move modal */
  const [contextMenu, setContextMenu] = useState(null);   // { thread, anchor }
  const [moveTarget, setMoveTarget] = useState(null);     // { thread, targetCategory }

  /* Sync view with route */
  const routeView = viewFromPath(location.pathname);
  useEffect(() => {
    if (routeView !== currentView) {
      dispatch(setView(routeView));
    }
  }, [routeView, currentView, dispatch]);

  /* Sync the URL ?category= → Redux slice. URL is the source of truth. */
  useEffect(() => {
    const desired = urlCategory === 'all' ? null : urlCategory;
    if (desired !== sliceCategory) {
      dispatch(setCategory(desired));
    }
  }, [urlCategory, sliceCategory, dispatch]);

  /* Fetch threads when view OR category changes */
  useEffect(() => {
    dispatch(fetchThreads({ view: currentView, category: urlCategory }));
  }, [currentView, urlCategory, dispatch]);

  /* Category counts: fetch on inbox mount and refresh whenever the
     thread list reloads (read/unread toggles, moves, periodic syncs all
     route through fetchThreads). */
  useEffect(() => {
    if (currentView !== 'inbox') return;
    dispatch(fetchCategoryCounts());
  }, [currentView, listStatus, dispatch]);

  /* Auto-poll inbox every 60s while tab is visible. Selection/detail pane are
     preserved because fetchThreads only rewrites the list — not the selected id. */
  useEffect(() => {
    if (currentView !== 'inbox') return;

    const POLL_MS = 60_000;
    let intervalId = null;

    const refresh = () => {
      dispatch(fetchThreads({ view: 'inbox', category: urlCategory }));
    };

    const start = () => {
      if (intervalId) return;
      intervalId = setInterval(refresh, POLL_MS);
    };
    const stop = () => {
      if (intervalId) {
        clearInterval(intervalId);
        intervalId = null;
      }
    };

    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        // Refresh immediately on return, then resume polling
        refresh();
        start();
      } else {
        stop();
      }
    };

    if (document.visibilityState === 'visible') start();
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      stop();
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [currentView, urlCategory, dispatch]);

  /* Deep-link: auto-select thread from URL param */
  useEffect(() => {
    if (urlThreadId && urlThreadId !== selectedId) {
      dispatch(selectThread(urlThreadId));
    }
  }, [urlThreadId, selectedId, dispatch]);

  /* Fetch thread detail when selection changes */
  useEffect(() => {
    if (selectedId) {
      dispatch(fetchThreadDetail(selectedId));
      dispatch(markRead(selectedId));
    }
  }, [selectedId, dispatch]);

  const handleSelectThread = (threadId) => {
    dispatch(selectThread(threadId));
  };

  const handleCompose = () => {
    window.dispatchEvent(new CustomEvent('devemail:compose', { detail: {} }));
  };

  /* Pill / sidebar category change → write the URL param. The URL → slice
     effect above will sync state. */
  const handleCategoryChange = useCallback((next) => {
    setSearchParams((prev) => {
      const sp = new URLSearchParams(prev);
      if (next === 'all') sp.delete('category');
      else sp.set('category', next);
      return sp;
    });
  }, [setSearchParams]);

  const handleContextMenu = (thread, anchor) => {
    setContextMenu({ thread, anchor });
  };

  const closeContextMenu = () => setContextMenu(null);

  const openMoveModal = (thread, targetCategory) => {
    setMoveTarget({ thread, targetCategory });
  };

  const closeMoveModal = () => setMoveTarget(null);

  const handleConfirmMove = async ({ applyToDomain, applyToExisting }) => {
    if (!moveTarget) return;
    const { thread, targetCategory } = moveTarget;
    const messageId = thread.latest_message_id;
    if (!messageId) {
      throw new Error('This thread has no underlying message id — cannot move.');
    }
    const result = await dispatch(setMessageCategory({
      messageId,
      category: targetCategory,
      applyToDomain,
      applyToExisting,
    })).unwrap();
    // Sweep feedback: include count when more than the target message moved.
    const sweptCount = result?.applied_to_existing_count || 0;
    const targetLabel = targetCategory === 'bulk' ? 'Bulk' : 'People';
    const totalMoved = sweptCount + 1;
    const message = totalMoved > 1
      ? `Moved ${totalMoved} messages to ${targetLabel}`
      : `Moved to ${targetLabel}`;
    dispatch(showToast({ message, duration: 2500 }));
    setMoveTarget(null);
  };

  // Build context-menu items for the right-clicked thread.
  const buildMenuItems = (thread) => {
    // Inbox category is determined by the latest message — show the
    // OPPOSITE move action so a click flips the bucket.
    // We don't have message-level category on the thread payload, so we
    // approximate via "everything I see in the bulk view is bulk." If
    // the user is in 'all', default to "Move to Bulk" (the more common
    // action for cleaning the inbox).
    const inferred = urlCategory === 'bulk' ? 'bulk' : 'people';
    const target = inferred === 'people' ? 'bulk' : 'people';
    const targetLabel = target === 'bulk' ? 'Bulk' : 'People';
    return [
      {
        label: `Move to ${targetLabel}`,
        onClick: () => openMoveModal(thread, target),
      },
    ];
  };

  return (
    <div className={styles.inbox}>
      {/* Left panel — thread list */}
      <div className={styles.listPanel}>
        <div className={styles.listHeader}>
          <h2 className={styles.viewTitle}>
            {currentView.startsWith('folder/')
              ? (folders.find((f) => f.id === currentView.slice(7))?.name || 'Folder')
              : VIEW_LABELS[currentView]}
          </h2>
          <div className={styles.listHeaderRight}>
            {threads.length > 0 && (
              <span className={styles.threadCount}>{threads.length}</span>
            )}
            <button
              className={styles.composeBtn}
              onClick={handleCompose}
              title="Compose new message"
              type="button"
            >
              <PenSquare size={16} />
            </button>
          </div>
        </div>

        {/* Pill row sits above the list, only on Inbox view */}
        {currentView === 'inbox' && (
          <CategoryPills
            activeCategory={urlCategory}
            counts={counts}
            onChange={handleCategoryChange}
          />
        )}

        <ThreadList
          threads={threads}
          status={listStatus}
          selectedId={selectedId}
          onSelect={handleSelectThread}
          onContextMenu={currentView === 'inbox' ? handleContextMenu : undefined}
        />
      </div>

      {/* Right panel — thread detail or empty state */}
      <div className={styles.detailPanel}>
        {selectedId ? (
          <ThreadDetail thread={threadDetail} status={detailStatus} />
        ) : (
          <EmptyState
            view={currentView}
            listIsEmpty={threads.length === 0 && listStatus === 'succeeded'}
            activeCategory={urlCategory}
          />
        )}
      </div>

      {contextMenu && (
        <ContextMenu
          anchor={contextMenu.anchor}
          items={buildMenuItems(contextMenu.thread)}
          onClose={closeContextMenu}
        />
      )}

      <MoveCategoryModal
        open={!!moveTarget}
        fromAddress={moveTarget?.thread?.latest_from_address}
        targetCategory={moveTarget?.targetCategory}
        onCancel={closeMoveModal}
        onConfirm={handleConfirmMove}
      />
    </div>
  );
}
