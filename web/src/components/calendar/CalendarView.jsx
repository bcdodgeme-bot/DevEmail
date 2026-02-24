import { useMemo } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  Calendar as CalIcon,
} from 'lucide-react';
import { format, startOfMonth, endOfMonth, startOfWeek, endOfWeek, addDays,
         isSameMonth, isSameDay, isToday, startOfDay, addHours } from 'date-fns';
import styles from './CalendarView.module.css';

const VIEW_MODES = [
  { key: 'month', label: 'Month' },
  { key: 'week', label: 'Week' },
  { key: 'day', label: 'Day' },
];

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

/**
 * CalendarView — main calendar grid.
 * Handles month, week, and day views.
 */
export default function CalendarView({
  currentDate,
  viewMode,
  events,
  calendars,
  selectedDate,
  onNavigate,
  onToday,
  onViewModeChange,
  onDateSelect,
  onEventClick,
  onAddEvent,
  syncButton,
}) {
  const current = new Date(currentDate);

  /* Header title based on view mode */
  const headerTitle = useMemo(() => {
    if (viewMode === 'month') return format(current, 'MMMM yyyy');
    if (viewMode === 'week') {
      const weekStart = startOfWeek(current);
      const weekEnd = endOfWeek(current);
      return `${format(weekStart, 'MMM d')} – ${format(weekEnd, 'MMM d, yyyy')}`;
    }
    return format(current, 'EEEE, MMMM d, yyyy');
  }, [current, viewMode]);

  /* Calendar color lookup */
  const calColorMap = useMemo(() => {
    const map = {};
    (calendars || []).forEach((cal) => {
      map[cal.id] = cal.color || 'var(--accent-purple)';
    });
    return map;
  }, [calendars]);

  /* Get events for a specific day */
  const eventsForDay = (day) => {
    return events.filter((evt) => {
      const evtDate = new Date(evt.start_at);
      return isSameDay(evtDate, day);
    });
  };

  /* ── MONTH VIEW ── */
  const renderMonth = () => {
    const monthStart = startOfMonth(current);
    const monthEnd = endOfMonth(current);
    const calStart = startOfWeek(monthStart);
    const calEnd = endOfWeek(monthEnd);

    const weeks = [];
    let day = calStart;

    while (day <= calEnd) {
      const week = [];
      for (let i = 0; i < 7; i++) {
        const d = day;
        const dayEvents = eventsForDay(d);
        const isCurrentMonth = isSameMonth(d, current);
        const isSelected = selectedDate && isSameDay(d, new Date(selectedDate));

        week.push(
          <button
            key={d.toISOString()}
            className={`${styles.dayCell} ${
              !isCurrentMonth ? styles.outsideMonth : ''
            } ${isToday(d) ? styles.today : ''} ${
              isSelected ? styles.selectedDay : ''
            }`}
            onClick={() => onDateSelect(d.toISOString())}
            type="button"
          >
            <span className={styles.dayNumber}>{format(d, 'd')}</span>
            {dayEvents.length > 0 && (
              <div className={styles.eventDots}>
                {dayEvents.slice(0, 3).map((evt) => (
                  <span
                    key={evt.id}
                    className={styles.eventDot}
                    style={{ background: calColorMap[evt.calendar_id] || 'var(--accent-purple)' }}
                    title={evt.title}
                  />
                ))}
                {dayEvents.length > 3 && (
                  <span className={styles.moreCount}>+{dayEvents.length - 3}</span>
                )}
              </div>
            )}
          </button>
        );
        day = addDays(day, 1);
      }
      weeks.push(
        <div key={`week-${weeks.length}`} className={styles.weekRow}>
          {week}
        </div>
      );
    }

    return (
      <div className={styles.monthGrid}>
        <div className={styles.weekdayHeader}>
          {WEEKDAYS.map((wd) => (
            <span key={wd} className={styles.weekdayLabel}>{wd}</span>
          ))}
        </div>
        {weeks}
      </div>
    );
  };

  /* ── WEEK VIEW ── */
  const renderWeek = () => {
    const weekStart = startOfWeek(current);
    const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));

    return (
      <div className={styles.weekView}>
        {/* Day headers */}
        <div className={styles.weekHeader}>
          <div className={styles.timeGutter} />
          {days.map((d) => (
            <div
              key={d.toISOString()}
              className={`${styles.weekDayHeader} ${isToday(d) ? styles.todayHeader : ''}`}
            >
              <span className={styles.weekDayName}>{format(d, 'EEE')}</span>
              <span className={styles.weekDayNum}>{format(d, 'd')}</span>
            </div>
          ))}
        </div>

        {/* Time grid */}
        <div className={styles.weekBody}>
          {HOURS.map((hour) => (
            <div key={hour} className={styles.hourRow}>
              <div className={styles.timeGutter}>
                <span className={styles.timeLabel}>
                  {hour === 0 ? '' : format(addHours(startOfDay(current), hour), 'h a')}
                </span>
              </div>
              {days.map((d) => {
                const cellStart = addHours(startOfDay(d), hour);
                const cellEvents = events.filter((evt) => {
                  const evtDate = new Date(evt.start_at);
                  return isSameDay(evtDate, d) && evtDate.getHours() === hour;
                });
                return (
                  <div
                    key={`${d.toISOString()}-${hour}`}
                    className={styles.weekCell}
                    onClick={() => {
                      onDateSelect(cellStart.toISOString());
                    }}
                  >
                    {cellEvents.map((evt) => (
                      <button
                        key={evt.id}
                        className={styles.weekEvent}
                        style={{
                          borderLeftColor: calColorMap[evt.calendar_id] || 'var(--accent-purple)',
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          onEventClick(evt.id);
                        }}
                        type="button"
                      >
                        {evt.title}
                      </button>
                    ))}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    );
  };

  /* ── DAY VIEW ── */
  const renderDay = () => {
    return (
      <div className={styles.dayView}>
        <div className={styles.dayHeader}>
          <span className={`${styles.dayViewTitle} ${isToday(current) ? styles.todayHeader : ''}`}>
            {format(current, 'EEEE, MMMM d')}
          </span>
        </div>
        <div className={styles.dayBody}>
          {HOURS.map((hour) => {
            const cellStart = addHours(startOfDay(current), hour);
            const hourEvents = events.filter((evt) => {
              const evtDate = new Date(evt.start_at);
              return isSameDay(evtDate, current) && evtDate.getHours() === hour;
            });
            return (
              <div key={hour} className={styles.dayHourRow}>
                <div className={styles.timeGutter}>
                  <span className={styles.timeLabel}>
                    {hour === 0 ? '' : format(cellStart, 'h a')}
                  </span>
                </div>
                <div
                  className={styles.dayHourCell}
                  onClick={() => onDateSelect(cellStart.toISOString())}
                >
                  {hourEvents.map((evt) => (
                    <button
                      key={evt.id}
                      className={styles.dayEvent}
                      style={{
                        borderLeftColor: calColorMap[evt.calendar_id] || 'var(--accent-purple)',
                      }}
                      onClick={(e) => {
                        e.stopPropagation();
                        onEventClick(evt.id);
                      }}
                      type="button"
                    >
                      <span className={styles.dayEventTime}>
                        {format(new Date(evt.start_at), 'h:mm a')}
                      </span>
                      <span className={styles.dayEventTitle}>{evt.title}</span>
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div className={styles.container}>
      {/* Toolbar */}
      <div className={styles.toolbar}>
        <div className={styles.toolbarLeft}>
          <button className={styles.todayBtn} onClick={onToday} type="button">
            Today
          </button>
          <button
            className={styles.navBtn}
            onClick={() => onNavigate(-1)}
            title="Previous"
            type="button"
          >
            <ChevronLeft size={16} />
          </button>
          <button
            className={styles.navBtn}
            onClick={() => onNavigate(1)}
            title="Next"
            type="button"
          >
            <ChevronRight size={16} />
          </button>
          <h2 className={styles.title}>{headerTitle}</h2>
        </div>

        <div className={styles.toolbarRight}>
          {syncButton}
          <div className={styles.viewToggle}>
            {VIEW_MODES.map(({ key, label }) => (
              <button
                key={key}
                className={`${styles.viewBtn} ${viewMode === key ? styles.viewBtnActive : ''}`}
                onClick={() => onViewModeChange(key)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
          <button className={styles.addBtn} onClick={onAddEvent} type="button">
            <Plus size={16} />
          </button>
        </div>
      </div>

      {/* Grid */}
      <div className={styles.grid}>
        {viewMode === 'month' && renderMonth()}
        {viewMode === 'week' && renderWeek()}
        {viewMode === 'day' && renderDay()}
      </div>
    </div>
  );
}
