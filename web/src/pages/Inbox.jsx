import { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useLocation } from 'react-router-dom';
import {
  fetchThreads,
  fetchThreadDetail,
  markRead,
  setView,
  selectThread,
  selectThreads,
  selectListStatus,
  selectSelectedThreadId,
  selectThreadDetail,
  selectDetailStatus,
  selectView,
} from '../store/inboxSlice';
import ThreadList from '../components/inbox/ThreadList';
import ThreadDetail from '../components/inbox/ThreadDetail';
import EmptyState from '../components/inbox/EmptyState';
import styles from './Inbox.module.css';

/** Map route pathname → API view name */
function viewFromPath(pathname) {
  if (pathname.startsWith('/sent')) return 'sent';
  if (pathname.startsWith('/drafts')) return 'drafts';
  if (pathname.startsWith('/trash')) return 'trash';
  return 'inbox';
}

const VIEW_LABELS = {
  inbox: 'Inbox',
  sent: 'Sent',
  drafts: 'Drafts',
  trash: 'Trash',
};

export default function Inbox() {
  const dispatch = useDispatch();
  const location = useLocation();

  const threads = useSelector(selectThreads);
  const listStatus = useSelector(selectListStatus);
  const selectedId = useSelector(selectSelectedThreadId);
  const threadDetail = useSelector(selectThreadDetail);
  const detailStatus = useSelector(selectDetailStatus);
  const currentView = useSelector(selectView);

  /* Sync view with route */
  const routeView = viewFromPath(location.pathname);
  useEffect(() => {
    if (routeView !== currentView) {
      dispatch(setView(routeView));
    }
  }, [routeView, currentView, dispatch]);

  /* Fetch threads when view changes */
  useEffect(() => {
    dispatch(fetchThreads({ view: currentView }));
  }, [currentView, dispatch]);

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

  return (
    <div className={styles.inbox}>
      {/* Left panel — thread list */}
      <div className={styles.listPanel}>
        <div className={styles.listHeader}>
          <h2 className={styles.viewTitle}>{VIEW_LABELS[currentView]}</h2>
          {threads.length > 0 && (
            <span className={styles.threadCount}>{threads.length}</span>
          )}
        </div>
        <ThreadList
          threads={threads}
          status={listStatus}
          selectedId={selectedId}
          onSelect={handleSelectThread}
        />
      </div>

      {/* Right panel — thread detail or empty state */}
      <div className={styles.detailPanel}>
        {selectedId ? (
          <ThreadDetail
            thread={threadDetail}
            status={detailStatus}
          />
        ) : (
          <EmptyState view={currentView} />
        )}
      </div>
    </div>
  );
}
