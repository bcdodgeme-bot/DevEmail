"""
Google Calendar Sync Service

Syncs calendars and events from Google Calendar API
into the local database using OAuth tokens.

Includes cross-account deduplication: if the same calendar
(by remote_id) already exists for this user under a different
account, it is skipped to prevent duplicate events.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.calendar import Calendar, Event
from app.services.google_oauth import refresh_google_token

logger = logging.getLogger(__name__)

GCAL_API = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarSyncService:
    """Sync Google Calendar data for a single account."""

    def __init__(self, db: AsyncSession, account: Account):
        self.db = db
        self.account = account
        self.access_token = account.oauth_token
        self._http = None

    async def _get_http(self):
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    async def close(self):
        if self._http:
            await self._http.aclose()
            self._http = None

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        http = await self._get_http()
        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = await http.request(method, url, headers=headers, **kwargs)

        if response.status_code == 401:
            await self._refresh_token()
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = await http.request(method, url, headers=headers, **kwargs)

        response.raise_for_status()
        return response.json()

    async def _refresh_token(self):
        if not self.account.oauth_refresh_token:
            raise Exception(f"No refresh token for {self.account.email_address}")
        token_data = await refresh_google_token(self.account.oauth_refresh_token)
        self.access_token = token_data["access_token"]
        self.account.oauth_token = self.access_token
        if "refresh_token" in token_data:
            self.account.oauth_refresh_token = token_data["refresh_token"]
        await self.db.commit()

    async def sync_calendars(self) -> list[Calendar]:
        """Sync calendar list from Google, with cross-account dedup."""
        data = await self._request("GET", f"{GCAL_API}/users/me/calendarList")
        items = data.get("items", [])
        synced = []

        for item in items:
            gcal_id = item["id"]
            name = item.get("summary", "Untitled")
            color = item.get("backgroundColor")

            # Check if this calendar already exists for THIS account
            result = await self.db.execute(
                select(Calendar).where(
                    Calendar.account_id == self.account.id,
                    Calendar.remote_id == gcal_id,
                )
            )
            calendar = result.scalar_one_or_none()

            if calendar:
                # Already exists under this account — update name/color
                calendar.name = name
                calendar.color = color
                synced.append(calendar)
                continue

            # DEDUP CHECK: Does this calendar already exist for this USER
            # under a DIFFERENT account? If so, skip it.
            result = await self.db.execute(
                select(Calendar).where(
                    Calendar.user_id == self.account.user_id,
                    Calendar.remote_id == gcal_id,
                )
            )
            existing_for_user = result.scalar_one_or_none()

            if existing_for_user:
                # Already synced via another account — skip
                logger.info(
                    f"Skipping calendar '{name}' ({gcal_id}) for "
                    f"{self.account.email_address} — already synced under "
                    f"account {existing_for_user.account_id}"
                )
                continue

            # Brand new calendar — create it
            calendar = Calendar(
                user_id=self.account.user_id,
                account_id=self.account.id,
                name=name,
                color=color,
                remote_id=gcal_id,
                sync_enabled=True,
            )
            self.db.add(calendar)
            synced.append(calendar)

        await self.db.commit()
        logger.info(f"Synced {len(synced)} calendars for {self.account.email_address}")
        return synced

    async def sync_events(self, calendar: Calendar, max_results: int = 250) -> int:
        """Sync events for a specific calendar from Google."""
        if not calendar.remote_id:
            return 0

        # Fetch events from last 30 days to next 365 days
        now = datetime.now(timezone.utc)
        time_min = datetime(now.year, now.month, 1, tzinfo=timezone.utc).isoformat()
        time_max = datetime(now.year + 1, now.month, now.day, tzinfo=timezone.utc).isoformat()

        params = {
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": max_results,
            "singleEvents": "false",  # Keep recurring events as-is with RRULE
            "orderBy": "updated",
        }

        try:
            data = await self._request(
                "GET",
                f"{GCAL_API}/calendars/{calendar.remote_id}/events",
                params=params,
            )
        except Exception as e:
            logger.error(f"Failed to fetch events for {calendar.name}: {e}")
            return 0

        items = data.get("items", [])
        new_count = 0

        for item in items:
            gcal_event_id = item["id"]
            status = item.get("status", "confirmed")

            if status == "cancelled":
                # Delete locally if we have it
                result = await self.db.execute(
                    select(Event).where(
                        Event.calendar_id == calendar.id,
                        Event.remote_id == gcal_event_id,
                    )
                )
                existing = result.scalar_one_or_none()
                if existing:
                    await self.db.delete(existing)
                continue

            # Skip events with "Cancelled:" or "Canceled:" in title
            event_title = item.get("summary", "Untitled")
            if event_title.lower().startswith("cancelled:") or event_title.lower().startswith("canceled:"):
                # Remove locally if we previously synced it
                result = await self.db.execute(
                    select(Event).where(
                        Event.calendar_id == calendar.id,
                        Event.remote_id == gcal_event_id,
                    )
                )
                existing = result.scalar_one_or_none()
                if existing:
                    await self.db.delete(existing)
                continue

            # Parse times
            start_data = item.get("start", {})
            end_data = item.get("end", {})
            all_day = "date" in start_data and "dateTime" not in start_data

            start_at = _parse_gcal_datetime(start_data)
            end_at = _parse_gcal_datetime(end_data)

            if not start_at:
                continue

            # Recurrence
            recurrence = item.get("recurrence", [])
            rrule = None
            for r in recurrence:
                if r.upper().startswith("RRULE:"):
                    rrule = r
                    break

            # Extract rich fields
            attendees_raw = item.get("attendees", [])
            attendees = [
                {
                    "name": a.get("displayName", ""),
                    "email": a.get("email", ""),
                    "response_status": a.get("responseStatus", "needsAction"),
                }
                for a in attendees_raw
            ]

            organizer = item.get("organizer", {})
            organizer_name = organizer.get("displayName")
            organizer_email = organizer.get("email")

            # Conference / Google Meet link
            conference_link = None
            conference_data = item.get("conferenceData")
            if conference_data:
                entry_points = conference_data.get("entryPoints", [])
                for ep in entry_points:
                    if ep.get("entryPointType") == "video":
                        conference_link = ep.get("uri")
                        break

            html_link = item.get("htmlLink")

            # Check if we already have this event
            result = await self.db.execute(
                select(Event).where(
                    Event.calendar_id == calendar.id,
                    Event.remote_id == gcal_event_id,
                )
            )
            event = result.scalar_one_or_none()

            if event:
                # Update existing event
                event.title = event_title
                event.description = item.get("description")
                event.location = item.get("location")
                event.start_at = start_at
                event.end_at = end_at
                event.all_day = all_day
                event.recurrence_rule = rrule
                event.attendees = attendees
                event.organizer_name = organizer_name
                event.organizer_email = organizer_email
                event.conference_link = conference_link
                event.html_link = html_link
                event.event_status = status
            else:
                # Create new event
                event = Event(
                    calendar_id=calendar.id,
                    title=event_title,
                    description=item.get("description"),
                    location=item.get("location"),
                    start_at=start_at,
                    end_at=end_at,
                    all_day=all_day,
                    recurrence_rule=rrule,
                    remote_id=gcal_event_id,
                    attendees=attendees,
                    organizer_name=organizer_name,
                    organizer_email=organizer_email,
                    conference_link=conference_link,
                    html_link=html_link,
                    event_status=status,
                )
                self.db.add(event)
                new_count += 1

        await self.db.commit()
        logger.info(
            f"Synced events for calendar '{calendar.name}': {new_count} new, {len(items)} total"
        )
        return new_count

    async def sync_all(self) -> dict:
        """Full sync: calendars + all events."""
        calendars = await self.sync_calendars()
        total_events = 0
        for cal in calendars:
            if cal.sync_enabled:
                count = await self.sync_events(cal)
                total_events += count
        return {"calendars": len(calendars), "events": total_events}


def _parse_gcal_datetime(data: dict) -> Optional[datetime]:
    """Parse Google Calendar date/dateTime into a datetime."""
    if not data:
        return None

    dt_str = data.get("dateTime") or data.get("date")
    if not dt_str:
        return None

    try:
        # dateTime format: 2024-01-15T10:00:00-05:00
        if "T" in dt_str:
            return datetime.fromisoformat(dt_str)
        else:
            # date format: 2024-01-15 (all-day event)
            return datetime.strptime(dt_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None
