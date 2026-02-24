"""
Notification Delivery Service

Delivers notifications via:
  1. In-app — stored in DB, fetched by frontend polling
  2. Email — sent via local Stalwart SMTP

Respects user preferences: quiet hours, enabled channels, reminder timing.
"""

import logging
import smtplib
import os
from datetime import datetime, time, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.notification import Notification, NotificationPreference

logger = logging.getLogger(__name__)

# Stalwart SMTP config
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "notifications@mail.damnitcarl.dev")


class NotificationService:
    """Delivers notifications to users."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_preferences(self, user_id) -> Optional[NotificationPreference]:
        result = await self.db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def notify_new_email(
        self,
        user: User,
        sender_name: str,
        sender_email: str,
        subject: str,
        message_id: Optional[str] = None,
    ):
        """Send a new-email notification if enabled."""
        prefs = await self.get_preferences(user.id)

        # Default: notify if no prefs exist
        if prefs and not prefs.notify_new_email:
            return

        if self._in_quiet_hours(prefs):
            logger.debug(f"Skipping notification for {user.email} — quiet hours")
            return

        title = f"New email from {sender_name}"
        body = subject or "(No subject)"

        # Always store in-app
        await self._store_in_app(user.id, "new_email", title, body, message_id)

        # Email notification
        if prefs and prefs.email_notifications:
            await self._send_email(
                to_email=user.email,
                subject=f"New email: {subject}",
                body_text=f"You have a new email from {sender_name} ({sender_email}).\n\nSubject: {subject}",
                body_html=self._new_email_html(sender_name, sender_email, subject),
            )

    async def notify_calendar_reminder(
        self,
        user: User,
        event_title: str,
        event_start: datetime,
        event_id: Optional[str] = None,
    ):
        """Send a calendar reminder notification if enabled."""
        prefs = await self.get_preferences(user.id)

        if prefs and not prefs.notify_calendar:
            return

        if self._in_quiet_hours(prefs):
            return

        time_str = event_start.strftime("%I:%M %p") if event_start else ""
        title = f"Reminder: {event_title}"
        body = f"Starting at {time_str}" if time_str else "Starting soon"

        await self._store_in_app(user.id, "calendar_reminder", title, body, event_id)

        if prefs and prefs.email_notifications:
            await self._send_email(
                to_email=user.email,
                subject=f"Reminder: {event_title} at {time_str}",
                body_text=f"Your event \"{event_title}\" starts at {time_str}.",
                body_html=self._calendar_reminder_html(event_title, time_str),
            )

    async def get_user_notifications(
        self,
        user_id,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Notification]:
        """Fetch in-app notifications for a user."""
        query = select(Notification).where(
            Notification.user_id == user_id
        ).order_by(Notification.created_at.desc()).limit(limit)

        if unread_only:
            query = query.where(Notification.read == False)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def mark_read(self, user_id, notification_id: str):
        """Mark a notification as read."""
        result = await self.db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
        notif = result.scalar_one_or_none()
        if notif:
            notif.read = True
            await self.db.commit()

    async def mark_all_read(self, user_id):
        """Mark all notifications as read for a user."""
        result = await self.db.execute(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.read == False,
            )
        )
        notifs = result.scalars().all()
        for n in notifs:
            n.read = True
        await self.db.commit()

    # --- Internal ---

    async def _store_in_app(
        self,
        user_id,
        category: str,
        title: str,
        body: str,
        reference_id: Optional[str] = None,
    ):
        """Store an in-app notification."""
        notif = Notification(
            user_id=user_id,
            category=category,
            title=title,
            body=body,
            reference_id=reference_id,
            read=False,
        )
        self.db.add(notif)
        await self.db.commit()
        logger.info(f"Stored in-app notification: {title}")

    async def _send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
    ):
        """Send an email notification via Stalwart SMTP."""
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = SMTP_FROM
            msg["To"] = to_email
            msg["Subject"] = subject

            msg.attach(MIMEText(body_text, "plain"))
            if body_html:
                msg.attach(MIMEText(body_html, "html"))

            # Use STARTTLS on port 587
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                if SMTP_PORT == 587:
                    server.starttls()
                if SMTP_USER and SMTP_PASS:
                    server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)

            logger.info(f"Email notification sent to {to_email}: {subject}")
        except Exception as e:
            logger.error(f"Failed to send email notification to {to_email}: {e}")

    def _in_quiet_hours(self, prefs: Optional[NotificationPreference]) -> bool:
        """Check if current time falls within user's quiet hours."""
        if not prefs or not prefs.quiet_start or not prefs.quiet_end:
            return False

        now = datetime.now(timezone.utc).time()
        start = prefs.quiet_start
        end = prefs.quiet_end

        if start <= end:
            return start <= now <= end
        else:
            # Wraps midnight (e.g. 22:00 → 07:00)
            return now >= start or now <= end

    def _new_email_html(self, sender_name: str, sender_email: str, subject: str) -> str:
        return f"""
        <div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px;">
            <h2 style="color: #333; font-size: 18px; margin: 0 0 16px;">New Email</h2>
            <div style="background: #f5f5f5; border-radius: 8px; padding: 16px;">
                <p style="margin: 0 0 8px;"><strong>From:</strong> {sender_name} &lt;{sender_email}&gt;</p>
                <p style="margin: 0;"><strong>Subject:</strong> {subject}</p>
            </div>
            <p style="color: #666; font-size: 13px; margin-top: 16px;">
                Open DevEmail to read and reply.
            </p>
        </div>
        """

    def _calendar_reminder_html(self, event_title: str, time_str: str) -> str:
        return f"""
        <div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px;">
            <h2 style="color: #333; font-size: 18px; margin: 0 0 16px;">📅 Event Reminder</h2>
            <div style="background: #f5f5f5; border-radius: 8px; padding: 16px;">
                <p style="margin: 0 0 8px; font-size: 16px; font-weight: 600;">{event_title}</p>
                <p style="margin: 0; color: #555;">Starting at {time_str}</p>
            </div>
            <p style="color: #666; font-size: 13px; margin-top: 16px;">
                Open DevEmail to view details.
            </p>
        </div>
        """
