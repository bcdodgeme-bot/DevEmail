from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.calendar import Calendar, Event
from app.schemas.calendar import (
    CalendarCreate,
    CalendarUpdate,
    CalendarResponse,
    CalendarListResponse,
    EventCreate,
    EventUpdate,
    EventResponse,
    EventListResponse,
)

router = APIRouter(prefix="/calendars", tags=["calendars"])


# --- Calendars ---

@router.get("", response_model=CalendarListResponse)
async def list_calendars(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all calendars for the current user."""
    result = await db.execute(
        select(Calendar)
        .where(Calendar.user_id == user.id)
        .order_by(Calendar.created_at)
    )
    calendars = result.scalars().all()
    return CalendarListResponse(
        calendars=[_to_calendar_response(c) for c in calendars],
        total=len(calendars),
    )


@router.post("", response_model=CalendarResponse, status_code=status.HTTP_201_CREATED)
async def create_calendar(
    request: CalendarCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new calendar."""
    calendar = Calendar(
        user_id=user.id,
        account_id=request.account_id,
        name=request.name,
        color=request.color,
        sync_enabled=request.sync_enabled,
    )
    db.add(calendar)
    await db.commit()
    await db.refresh(calendar)
    return _to_calendar_response(calendar)


@router.get("/{calendar_id}", response_model=CalendarResponse)
async def get_calendar(
    calendar_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific calendar."""
    calendar = await _get_calendar_or_404(db, user.id, calendar_id)
    return _to_calendar_response(calendar)


@router.patch("/{calendar_id}", response_model=CalendarResponse)
async def update_calendar(
    calendar_id: str,
    request: CalendarUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a calendar."""
    calendar = await _get_calendar_or_404(db, user.id, calendar_id)

    if request.name is not None:
        calendar.name = request.name
    if request.color is not None:
        calendar.color = request.color
    if request.sync_enabled is not None:
        calendar.sync_enabled = request.sync_enabled

    await db.commit()
    await db.refresh(calendar)
    return _to_calendar_response(calendar)


@router.delete("/{calendar_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calendar(
    calendar_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a calendar and all its events."""
    calendar = await _get_calendar_or_404(db, user.id, calendar_id)
    await db.delete(calendar)
    await db.commit()


# --- Events ---

@router.get("/events/all", response_model=EventListResponse)
async def list_all_events(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    calendar_id: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List events across all calendars with optional date range filter."""
    # Get user's calendar IDs
    cal_result = await db.execute(
        select(Calendar.id).where(Calendar.user_id == user.id)
    )
    user_calendar_ids = [row[0] for row in cal_result.all()]

    if not user_calendar_ids:
        return EventListResponse(events=[], total=0)

    query = select(Event).where(Event.calendar_id.in_(user_calendar_ids))

    if calendar_id:
        query = query.where(Event.calendar_id == calendar_id)
    if start:
        query = query.where(Event.end_at >= start)
    if end:
        query = query.where(Event.start_at <= end)

    query = query.order_by(Event.start_at)

    result = await db.execute(query)
    events = result.scalars().all()

    return EventListResponse(
        events=[_to_event_response(e) for e in events],
        total=len(events),
    )


@router.get("/{calendar_id}/events", response_model=EventListResponse)
async def list_calendar_events(
    calendar_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List events for a specific calendar."""
    calendar = await _get_calendar_or_404(db, user.id, calendar_id)

    query = select(Event).where(Event.calendar_id == calendar.id)

    if start:
        query = query.where(Event.end_at >= start)
    if end:
        query = query.where(Event.start_at <= end)

    query = query.order_by(Event.start_at)

    result = await db.execute(query)
    events = result.scalars().all()

    return EventListResponse(
        events=[_to_event_response(e) for e in events],
        total=len(events),
    )


@router.post("/{calendar_id}/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    calendar_id: str,
    request: EventCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new event."""
    calendar = await _get_calendar_or_404(db, user.id, calendar_id)

    event = Event(
        calendar_id=calendar.id,
        title=request.title,
        description=request.description,
        location=request.location,
        start_at=request.start_at,
        end_at=request.end_at,
        all_day=request.all_day,
        recurrence_rule=request.recurrence_rule,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return _to_event_response(event)


@router.get("/{calendar_id}/events/{event_id}", response_model=EventResponse)
async def get_event(
    calendar_id: str,
    event_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific event."""
    calendar = await _get_calendar_or_404(db, user.id, calendar_id)
    event = await _get_event_or_404(db, calendar.id, event_id)
    return _to_event_response(event)


@router.patch("/{calendar_id}/events/{event_id}", response_model=EventResponse)
async def update_event(
    calendar_id: str,
    event_id: str,
    request: EventUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an event."""
    calendar = await _get_calendar_or_404(db, user.id, calendar_id)
    event = await _get_event_or_404(db, calendar.id, event_id)

    if request.title is not None:
        event.title = request.title
    if request.description is not None:
        event.description = request.description
    if request.location is not None:
        event.location = request.location
    if request.start_at is not None:
        event.start_at = request.start_at
    if request.end_at is not None:
        event.end_at = request.end_at
    if request.all_day is not None:
        event.all_day = request.all_day
    if request.recurrence_rule is not None:
        event.recurrence_rule = request.recurrence_rule

    await db.commit()
    await db.refresh(event)
    return _to_event_response(event)


@router.delete("/{calendar_id}/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    calendar_id: str,
    event_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an event."""
    calendar = await _get_calendar_or_404(db, user.id, calendar_id)
    event = await _get_event_or_404(db, calendar.id, event_id)
    await db.delete(event)
    await db.commit()


# --- Helpers ---

async def _get_calendar_or_404(db, user_id, calendar_id: str) -> Calendar:
    result = await db.execute(
        select(Calendar).where(Calendar.id == calendar_id, Calendar.user_id == user_id)
    )
    calendar = result.scalar_one_or_none()
    if not calendar:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar not found")
    return calendar


async def _get_event_or_404(db, calendar_id, event_id: str) -> Event:
    result = await db.execute(
        select(Event).where(Event.id == event_id, Event.calendar_id == calendar_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


def _to_calendar_response(c: Calendar) -> CalendarResponse:
    return CalendarResponse(
        id=str(c.id),
        name=c.name,
        account_id=str(c.account_id) if c.account_id else None,
        color=c.color,
        sync_enabled=c.sync_enabled,
        created_at=c.created_at,
    )


def _to_event_response(e: Event) -> EventResponse:
    return EventResponse(
        id=str(e.id),
        calendar_id=str(e.calendar_id),
        title=e.title,
        description=e.description,
        location=e.location,
        start_at=e.start_at,
        end_at=e.end_at,
        all_day=e.all_day,
        recurrence_rule=e.recurrence_rule,
        created_at=e.created_at,
        updated_at=e.updated_at,
    )
