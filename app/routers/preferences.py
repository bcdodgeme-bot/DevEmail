"""
User Preferences & Privacy Endpoints

- Notification preferences (CRUD)
- Data export
- Account deletion
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from datetime import time as dt_time

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User, RefreshToken
from app.models.account import Account
from app.models.thread import Thread
from app.models.message import Message
from app.models.contact import Contact
from app.models.notification import NotificationPreference

router = APIRouter(prefix="/preferences", tags=["preferences"])


# --- Schemas ---

class NotificationPrefsResponse(BaseModel):
    notify_new_email: bool = True
    notify_calendar_reminder: bool = True
    reminder_minutes_before: int = 15
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None

class NotificationPrefsUpdate(BaseModel):
    notify_new_email: Optional[bool] = None
    notify_calendar_reminder: Optional[bool] = None
    reminder_minutes_before: Optional[int] = None
    quiet_hours_start: Optional[str] = None  # "HH:MM" format
    quiet_hours_end: Optional[str] = None    # "HH:MM" format


# --- Notification Preferences ---

@router.get("/notifications", response_model=NotificationPrefsResponse)
async def get_notification_prefs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get notification preferences for the current user."""
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user.id
        )
    )
    prefs = result.scalar_one_or_none()

    if not prefs:
        # Return defaults
        return NotificationPrefsResponse()

    return NotificationPrefsResponse(
        notify_new_email=prefs.notify_new_email,
        notify_calendar_reminder=prefs.notify_calendar_reminder,
        reminder_minutes_before=prefs.reminder_minutes_before,
        quiet_hours_start=prefs.quiet_hours_start.strftime("%H:%M") if prefs.quiet_hours_start else None,
        quiet_hours_end=prefs.quiet_hours_end.strftime("%H:%M") if prefs.quiet_hours_end else None,
    )


@router.put("/notifications", response_model=NotificationPrefsResponse)
async def update_notification_prefs(
    request: NotificationPrefsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update notification preferences."""
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user.id
        )
    )
    prefs = result.scalar_one_or_none()

    if not prefs:
        prefs = NotificationPreference(user_id=user.id)
        db.add(prefs)

    if request.notify_new_email is not None:
        prefs.notify_new_email = request.notify_new_email
    if request.notify_calendar_reminder is not None:
        prefs.notify_calendar_reminder = request.notify_calendar_reminder
    if request.reminder_minutes_before is not None:
        prefs.reminder_minutes_before = request.reminder_minutes_before
    if request.quiet_hours_start is not None:
        prefs.quiet_hours_start = _parse_time(request.quiet_hours_start)
    elif request.quiet_hours_start == "":
        prefs.quiet_hours_start = None
    if request.quiet_hours_end is not None:
        prefs.quiet_hours_end = _parse_time(request.quiet_hours_end)
    elif request.quiet_hours_end == "":
        prefs.quiet_hours_end = None

    await db.commit()
    await db.refresh(prefs)

    return NotificationPrefsResponse(
        notify_new_email=prefs.notify_new_email,
        notify_calendar_reminder=prefs.notify_calendar_reminder,
        reminder_minutes_before=prefs.reminder_minutes_before,
        quiet_hours_start=prefs.quiet_hours_start.strftime("%H:%M") if prefs.quiet_hours_start else None,
        quiet_hours_end=prefs.quiet_hours_end.strftime("%H:%M") if prefs.quiet_hours_end else None,
    )


# --- Data Export ---

@router.post("/export")
async def export_user_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export all user data as JSON."""
    # Accounts
    accounts_result = await db.execute(
        select(Account).where(Account.user_id == user.id)
    )
    accounts = accounts_result.scalars().all()

    # Contacts
    contacts_result = await db.execute(
        select(Contact).where(Contact.user_id == user.id)
    )
    contacts = contacts_result.scalars().all()

    # Threads + messages
    threads_result = await db.execute(
        select(Thread).where(Thread.user_id == user.id)
    )
    threads = threads_result.scalars().all()

    thread_ids = [t.id for t in threads]
    messages = []
    if thread_ids:
        messages_result = await db.execute(
            select(Message).where(Message.thread_id.in_(thread_ids))
        )
        messages = messages_result.scalars().all()

    export = {
        "user": {
            "email": user.email,
            "display_name": user.display_name,
            "timezone": user.timezone,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "accounts": [
            {
                "email_address": a.email_address,
                "provider": a.provider,
                "display_name": a.display_name,
            }
            for a in accounts
        ],
        "contacts_count": len(contacts),
        "contacts": [
            {
                "first_name": c.first_name,
                "last_name": c.last_name,
                "company": c.company,
                "emails": c.emails,
            }
            for c in contacts[:500]  # Cap at 500 for performance
        ],
        "threads_count": len(threads),
        "messages_count": len(messages),
    }

    return JSONResponse(
        content=export,
        headers={
            "Content-Disposition": 'attachment; filename="devemail-export.json"',
        },
    )


# --- Account Deletion ---

@router.delete("/account")
async def delete_account(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete the user account and all associated data."""
    # Delete in dependency order
    # Threads cascade to messages, messages cascade to attachments/unsubscribe
    await db.execute(delete(Thread).where(Thread.user_id == user.id))
    await db.execute(delete(Contact).where(Contact.user_id == user.id))
    await db.execute(delete(Account).where(Account.user_id == user.id))
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))
    await db.execute(
        delete(NotificationPreference).where(
            NotificationPreference.user_id == user.id
        )
    )
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()

    return {"message": "Account deleted"}


# --- Helpers ---

def _parse_time(time_str: str) -> dt_time | None:
    """Parse 'HH:MM' string to time object."""
    if not time_str:
        return None
    try:
        parts = time_str.split(":")
        return dt_time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None
