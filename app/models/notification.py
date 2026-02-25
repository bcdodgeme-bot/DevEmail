"""
Notification model — stores in-app notifications.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, Text, ForeignKey, DateTime, Integer, Time
from sqlalchemy.orm import relationship
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
    notify_calendar_reminder = Column(Boolean, default=True)
    reminder_minutes_before = Column(Integer, default=15)

    quiet_hours_start = Column(Time, nullable=True)
    quiet_hours_end = Column(Time, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    user = relationship("User", back_populates="notification_preferences")
