"""
Unsubscribe Execution Service

Handles one-click unsubscribe by:
- HTTP POST/GET to unsubscribe URLs
- Sending mailto: unsubscribe emails
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
import aiosmtplib
from email.mime.text import MIMEText

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.unsubscribe import UnsubscribeLink

logger = logging.getLogger(__name__)


class UnsubscribeService:
    """Execute unsubscribe actions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute(self, unsubscribe_link_id: str, user_email: str) -> dict:
        """
        Execute an unsubscribe action.

        Tries URL first (HTTP POST then GET), falls back to mailto.

        Returns:
            {"method": "url"|"email", "success": bool, "detail": str}
        """
        result = await self.db.execute(
            select(UnsubscribeLink).where(UnsubscribeLink.id == unsubscribe_link_id)
        )
        link = result.scalar_one_or_none()
        if not link:
            return {"method": None, "success": False, "detail": "Unsubscribe link not found"}

        # Prefer URL-based unsubscribe (RFC 8058 one-click)
        if link.unsubscribe_url:
            success, detail = await self._unsubscribe_via_url(link.unsubscribe_url)
            if success:
                link.executed = True
                link.executed_at = datetime.now(timezone.utc)
                await self.db.commit()
                return {"method": "url", "success": True, "detail": detail}

        # Fall back to mailto-based unsubscribe
        if link.unsubscribe_email:
            success, detail = await self._unsubscribe_via_email(
                link.unsubscribe_email, user_email
            )
            if success:
                link.executed = True
                link.executed_at = datetime.now(timezone.utc)
                await self.db.commit()
                return {"method": "email", "success": True, "detail": detail}

        return {
            "method": None,
            "success": False,
            "detail": "No valid unsubscribe method available",
        }

    async def _unsubscribe_via_url(self, url: str) -> tuple[bool, str]:
        """Hit the unsubscribe URL via HTTP POST (RFC 8058), fall back to GET."""
        try:
            async with httpx.AsyncClient(
                timeout=15.0,
                follow_redirects=True,
                headers={"User-Agent": "DevEmail-Unsubscribe/1.0"},
            ) as client:
                # RFC 8058: one-click unsubscribe uses POST with
                # List-Unsubscribe=One-Click body
                response = await client.post(
                    url,
                    content="List-Unsubscribe=One-Click",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                if response.status_code < 400:
                    logger.info(f"Unsubscribed via POST: {url} → {response.status_code}")
                    return True, f"HTTP POST {response.status_code}"

                # Fall back to GET
                response = await client.get(url)
                if response.status_code < 400:
                    logger.info(f"Unsubscribed via GET: {url} → {response.status_code}")
                    return True, f"HTTP GET {response.status_code}"

                logger.warning(f"Unsubscribe URL failed: {url} → {response.status_code}")
                return False, f"HTTP {response.status_code}"

        except Exception as e:
            logger.error(f"Unsubscribe URL error: {url} → {e}")
            return False, str(e)

    async def _unsubscribe_via_email(
        self, unsub_email: str, from_email: str
    ) -> tuple[bool, str]:
        """Send an unsubscribe email to the mailto address."""
        try:
            msg = MIMEText("unsubscribe", "plain", "utf-8")
            msg["From"] = from_email
            msg["To"] = unsub_email
            msg["Subject"] = "Unsubscribe"

            # Send via local Stalwart
            await aiosmtplib.send(
                msg,
                hostname="mail.damnitcarl.dev",
                port=465,
                use_tls=True,
            )

            logger.info(f"Sent unsubscribe email to {unsub_email} from {from_email}")
            return True, f"Email sent to {unsub_email}"

        except Exception as e:
            logger.error(f"Unsubscribe email error: {unsub_email} → {e}")
            return False, str(e)
