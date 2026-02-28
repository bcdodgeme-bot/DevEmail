from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


# --- Calendars ---

class CalendarCreate(BaseModel):
    name: str
    account_id: Optional[str] = None
    color: Optional[str] = None
    sync_enabled: bool = True


class CalendarUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    sync_enabled: Optional[bool] = None


class CalendarResponse(BaseModel):
    id: str
    name: str
    account_id: Optional[str] = None
    color: Optional[str] = None
    sync_enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CalendarListResponse(BaseModel):
    calendars: List[CalendarResponse]
    total: int


# --- Attendees ---

class AttendeeInfo(BaseModel):
    name: Optional[str] = None
    email: str
    response_status: Optional[str] = None  # accepted, declined, tentative, needsAction


# --- Events ---

class EventCreate(BaseModel):
    calendar_id: str
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    start_at: datetime
    end_at: Optional[datetime] = None
    all_day: bool = False
    recurrence_rule: Optional[str] = None


class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    all_day: Optional[bool] = None
    recurrence_rule: Optional[str] = None


class EventResponse(BaseModel):
    id: str
    calendar_id: str
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    start_at: datetime
    end_at: Optional[datetime] = None
    all_day: bool
    recurrence_rule: Optional[str] = None
    recurrence_human: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Rich fields
    attendees: Optional[List[AttendeeInfo]] = None
    organizer_name: Optional[str] = None
    organizer_email: Optional[str] = None
    conference_link: Optional[str] = None
    html_link: Optional[str] = None
    event_status: Optional[str] = None

    class Config:
        from_attributes = True


class EventListResponse(BaseModel):
    events: List[EventResponse]
    total: int
