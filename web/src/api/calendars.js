import { apiFetch } from '../utils/api';

export const calendarsAPI = {
  /* ── Calendars ── */

  async listCalendars() {
    return apiFetch('/calendars');
  },

  async createCalendar(data) {
    return apiFetch('/calendars', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async updateCalendar(calendarId, data) {
    return apiFetch(`/calendars/${calendarId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  async deleteCalendar(calendarId) {
    return apiFetch(`/calendars/${calendarId}`, { method: 'DELETE' });
  },

  /* ── Events ── */

  async listEvents({ calendarId, start, end } = {}) {
    const params = new URLSearchParams();
    if (calendarId) params.set('calendar_id', calendarId);
    if (start) params.set('start', start);
    if (end) params.set('end', end);
    return apiFetch(`/calendars/events?${params}`);
  },

  async getEvent(eventId) {
    return apiFetch(`/calendars/events/${eventId}`);
  },

  async createEvent(data) {
    return apiFetch('/calendars/events', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async updateEvent(eventId, data) {
    return apiFetch(`/calendars/events/${eventId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  async deleteEvent(eventId) {
    return apiFetch(`/calendars/events/${eventId}`, { method: 'DELETE' });
  },
};
