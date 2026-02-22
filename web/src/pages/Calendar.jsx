import { useEffect, useCallback, useMemo } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import {
  fetchCalendars,
  fetchEvents,
  createEvent,
  updateEvent,
  deleteEvent,
  setViewMode,
  setSelectedDate,
  selectEvent,
  clearEventSelection,
  openEditor,
  closeEditor,
  navigateMonth,
  navigateWeek,
  navigateDay,
  goToToday,
  selectCalendars,
  selectEvents,
  selectEventsStatus,
  selectViewMode,
  selectCurrentDate,
  selectSelectedDate,
  selectSelectedEvent,
  selectIsEditorOpen,
  selectEditingEvent,
} from '../store/calendarsSlice';
import CalendarView from '../components/calendar/CalendarView';
import EventDetail from '../components/calendar/EventDetail';
import EventEditor from '../components/calendar/EventEditor';
import styles from './Calendar.module.css';

export default function CalendarPage() {
  const dispatch = useDispatch();

  const calendars = useSelector(selectCalendars);
  const events = useSelector(selectEvents);
  const eventsStatus = useSelector(selectEventsStatus);
  const viewMode = useSelector(selectViewMode);
  const currentDate = useSelector(selectCurrentDate);
  const selectedDate = useSelector(selectSelectedDate);
  const selectedEvent = useSelector(selectSelectedEvent);
  const isEditorOpen = useSelector(selectIsEditorOpen);
  const editingEvent = useSelector(selectEditingEvent);

  /* Initial fetch */
  useEffect(() => {
    dispatch(fetchCalendars());
  }, [dispatch]);

  /* Fetch events when date range changes */
  useEffect(() => {
    const d = new Date(currentDate);
    const year = d.getFullYear();
    const month = d.getMonth();

    /* Fetch a wider range to cover week/day overflow */
    const start = new Date(year, month - 1, 1).toISOString();
    const end = new Date(year, month + 2, 0).toISOString();

    dispatch(fetchEvents({ start, end }));
  }, [currentDate, dispatch]);

  /* Navigation */
  const handleNavigate = useCallback(
    (direction) => {
      if (viewMode === 'month') dispatch(navigateMonth(direction));
      else if (viewMode === 'week') dispatch(navigateWeek(direction));
      else dispatch(navigateDay(direction));
    },
    [dispatch, viewMode]
  );

  const handleToday = useCallback(() => dispatch(goToToday()), [dispatch]);

  const handleViewModeChange = useCallback(
    (mode) => dispatch(setViewMode(mode)),
    [dispatch]
  );

  const handleDateSelect = useCallback(
    (date) => dispatch(setSelectedDate(date)),
    [dispatch]
  );

  const handleEventClick = useCallback(
    (eventId) => dispatch(selectEvent(eventId)),
    [dispatch]
  );

  const handleAddEvent = useCallback(
    () => dispatch(openEditor(null)),
    [dispatch]
  );

  const handleEditEvent = useCallback(
    (event) => dispatch(openEditor(event)),
    [dispatch]
  );

  const handleDeleteEvent = useCallback(
    (eventId) => {
      if (window.confirm('Delete this event?')) {
        dispatch(deleteEvent(eventId));
      }
    },
    [dispatch]
  );

  const handleCloseDetail = useCallback(
    () => dispatch(clearEventSelection()),
    [dispatch]
  );

  const handleSaveEvent = useCallback(
    (formData) => {
      if (editingEvent?.id) {
        dispatch(updateEvent({ eventId: editingEvent.id, data: formData }));
      } else {
        dispatch(createEvent(formData));
      }
    },
    [dispatch, editingEvent]
  );

  const handleCloseEditor = useCallback(
    () => dispatch(closeEditor()),
    [dispatch]
  );

  /* Find calendar for selected event */
  const selectedEventCalendar = useMemo(() => {
    if (!selectedEvent) return null;
    return calendars.find((c) => c.id === selectedEvent.calendar_id);
  }, [selectedEvent, calendars]);

  return (
    <div className={styles.calendar}>
      {/* Left panel — calendar grid */}
      <div className={styles.gridPanel}>
        <CalendarView
          currentDate={currentDate}
          viewMode={viewMode}
          events={events}
          calendars={calendars}
          selectedDate={selectedDate}
          onNavigate={handleNavigate}
          onToday={handleToday}
          onViewModeChange={handleViewModeChange}
          onDateSelect={handleDateSelect}
          onEventClick={handleEventClick}
          onAddEvent={handleAddEvent}
        />
      </div>

      {/* Right panel — event detail */}
      <div className={styles.detailPanel}>
        <EventDetail
          event={selectedEvent}
          calendar={selectedEventCalendar}
          onEdit={handleEditEvent}
          onDelete={handleDeleteEvent}
          onClose={handleCloseDetail}
        />
      </div>

      {/* Event editor modal */}
      {isEditorOpen && (
        <EventEditor
          event={editingEvent}
          calendars={calendars}
          defaultDate={selectedDate}
          onSave={handleSaveEvent}
          onClose={handleCloseEditor}
        />
      )}
    </div>
  );
}
