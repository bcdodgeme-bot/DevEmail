"""
Notification model — stores in-app notifications.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    category = Column(String(50), nullable=False)  # new_email, calendar_reminder, system
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    reference_id = Column(String(255), nullable=True)  # message_id or event_id for deep linking

    read = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    notify_new_email = Column(Boolean, default=True)
    notify_calendar = Column(Boolean, default=True)
    email_notifications = Column(Boolean, default=False)
    reminder_minutes = Column(String(10), default="15")  # minutes before event

    quiet_start = Column(String(5), nullable=True)  # "22:00"
    quiet_end = Column(String(5), nullable=True)    # "07:00"

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
