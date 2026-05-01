"""
Email Send Service

Sends email through the appropriate transport based on account type:
- Gmail accounts: Gmail API (uses OAuth token)
- Stalwart accounts: SMTP via aiosmtplib
"""

import base64
import logging
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timezone
from typing import Optional

import httpx
import aiosmtplib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import update as sa_update
from app.config import settings
from app.models.account import Account
from app.models.signature import Signature
from app.models.thread import Thread
from app.models.message import Message
from app.services.google_oauth import refresh_google_token

logger = logging.getLogger(__name__)

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


def _tracking_pixel_html(token: uuid.UUID) -> str:
    """Build the 1x1 tracking pixel tag that fires when the recipient
    loads the email. Placed right before </body> when possible."""
    url = f"{settings.APP_URL.rstrip('/')}/api/track/open/{token}"
    return (
        f'<img src="{url}" width="1" height="1" alt="" '
        f'style="display:block;width:1px;height:1px;border:0;" />'
    )


def _inject_tracking_pixel(body_html: Optional[str], token: uuid.UUID) -> Optional[str]:
    """Append the tracking pixel to body_html. If the HTML has a closing
    </body> tag, insert immediately before it; otherwise append to the end."""
    if not body_html:
        return body_html
    pixel = _tracking_pixel_html(token)
    lower = body_html.lower()
    idx = lower.rfind("</body>")
    if idx != -1:
        return body_html[:idx] + pixel + body_html[idx:]
    return body_html + pixel


class EmailSendService:
    """Send email through Gmail API or Stalwart SMTP."""

    def __init__(self, db: AsyncSession, account: Account):
        self.db = db
        self.account = account

    async def send_from_draft(
        self,
        draft_message: Message,
        *,
        to: list[dict],
        subject: str,
        body_html: Optional[str] = None,
        body_text: Optional[str] = None,
        cc: list[dict] = None,
        bcc: list[dict] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
        signature_id: Optional[str] = None,
        read_receipt: bool = False,
        attachments: list[dict] = None,
    ) -> dict:
        """
        Send an email FROM an already-persisted draft Message.

        The draft (along with its on-disk attachments and DB Attachment rows)
        was created up front by the compose endpoint. This method:
          1. Builds the MIME message — same format as `send()`.
          2. Hands off to the provider transport.
          3. ON SUCCESS: updates the draft in place (is_draft=false,
             is_sent=true, sent_at, remote_id, body_html w/ tracking pixel).
             Attachment rows already point at this Message id, so they
             travel with it into the Sent folder automatically.
          4. ON FAILURE: raises. Caller leaves the draft untouched —
             user retries from the Drafts folder. (Phase 9 design choice
             iii: don't lose the user's work on a transient SMTP error.)

        Note: existing send() (used by tests/scripts) is preserved
        unchanged. This is a new path specifically for the
        attachment-aware compose flow.
        """
        cc = cc or []
        bcc = bcc or []
        attachments = attachments or []

        if signature_id:
            body_html, body_text = await self._append_signature(
                signature_id, body_html, body_text
            )

        tracking_token = uuid.uuid4() if body_html else None
        if tracking_token:
            body_html = _inject_tracking_pixel(body_html, tracking_token)

        mime_msg = self._build_mime(
            to=to,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            cc=cc,
            bcc=bcc,
            in_reply_to=in_reply_to,
            references=references,
            read_receipt=read_receipt,
            attachments=attachments,
        )

        # Provider call. Raises on failure → caller's exception handler
        # leaves the draft intact.
        if self.account.provider == "gmail":
            remote_id = await self._send_gmail(mime_msg)
        elif self.account.provider == "stalwart":
            remote_id = await self._send_smtp(mime_msg)
        else:
            raise Exception(f"Unknown provider: {self.account.provider}")

        # Flip the draft → sent in place.
        now = datetime.now(timezone.utc)
        draft_message.is_draft = False
        draft_message.is_sent = True
        draft_message.sent_at = now
        draft_message.received_at = now
        draft_message.remote_id = remote_id
        if tracking_token is not None:
            draft_message.tracking_token = tracking_token
        # Persist the body w/ tracking pixel so the Sent-folder view shows
        # what was actually sent.
        if body_html is not None:
            draft_message.body_html = body_html
        if body_text is not None:
            draft_message.body_text = body_text
        draft_message.has_attachments = len(attachments) > 0
        await self.db.flush()

        # Bump thread metadata to reflect the new send.
        await self.db.execute(
            sa_update(Thread)
            .where(Thread.id == draft_message.thread_id)
            .values(last_message_at=now)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()

        logger.info(
            "Sent email (from draft) via %s from %s to %s",
            self.account.provider, self.account.email_address, to,
        )

        return {
            "message_id": str(draft_message.id),
            "thread_id": str(draft_message.thread_id),
            "remote_id": remote_id,
        }

    async def send(
        self,
        to: list[dict],
        subject: str,
        body_html: Optional[str] = None,
        body_text: Optional[str] = None,
        cc: list[dict] = None,
        bcc: list[dict] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
        signature_id: Optional[str] = None,
        read_receipt: bool = False,
        attachments: list[dict] = None,
    ) -> dict:
        """
        Send an email.

        Args:
            to: List of {"name": "...", "address": "..."}
            subject: Email subject
            body_html: HTML body
            body_text: Plain text body
            cc: CC recipients
            bcc: BCC recipients
            in_reply_to: Message-ID header of message being replied to
            references: References header for threading
            signature_id: ID of signature to append
            read_receipt: Request a read receipt
            attachments: List of {"filename": "...", "content_type": "...", "data": bytes}

        Returns:
            {"message_id": "...", "thread_id": "...", "remote_id": "..."}
        """
        cc = cc or []
        bcc = bcc or []
        attachments = attachments or []

        # Append signature if specified
        if signature_id:
            body_html, body_text = await self._append_signature(
                signature_id, body_html, body_text
            )

        # Open tracking: mint a token and inject a 1x1 pixel into the HTML body.
        # The pixel fires when the recipient's mail client loads images.
        tracking_token = uuid.uuid4() if body_html else None
        if tracking_token:
            body_html = _inject_tracking_pixel(body_html, tracking_token)

        # Build the MIME message
        mime_msg = self._build_mime(
            to=to,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            cc=cc,
            bcc=bcc,
            in_reply_to=in_reply_to,
            references=references,
            read_receipt=read_receipt,
            attachments=attachments,
        )

        # Route to the appropriate transport
        if self.account.provider == "gmail":
            remote_id = await self._send_gmail(mime_msg)
        elif self.account.provider == "stalwart":
            remote_id = await self._send_smtp(mime_msg)
        else:
            raise Exception(f"Unknown provider: {self.account.provider}")

        # Store sent message locally
        message = await self._store_sent_message(
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            in_reply_to=in_reply_to,
            references=references,
            remote_id=remote_id,
            read_receipt=read_receipt,
            attachments=attachments,
            tracking_token=tracking_token,
        )

        logger.info(f"Sent email via {self.account.provider} from {self.account.email_address} to {to}")

        return {
            "message_id": str(message.id),
            "thread_id": str(message.thread_id),
            "remote_id": remote_id,
        }

    def _build_mime(
        self,
        to: list[dict],
        subject: str,
        body_html: Optional[str],
        body_text: Optional[str],
        cc: list[dict],
        bcc: list[dict],
        in_reply_to: Optional[str],
        references: Optional[str],
        read_receipt: bool,
        attachments: list[dict],
    ) -> MIMEMultipart:
        """Build a MIME message."""
        msg = MIMEMultipart("mixed")

        # Headers
        from_str = self.account.display_name or self.account.email_address
        msg["From"] = f"{from_str} <{self.account.email_address}>"
        msg["To"] = ", ".join(_format_address(a) for a in to)
        msg["Subject"] = subject

        if cc:
            msg["Cc"] = ", ".join(_format_address(a) for a in cc)

        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references

        if read_receipt:
            msg["Disposition-Notification-To"] = self.account.email_address

        # Body
        if body_html and body_text:
            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(body_text, "plain", "utf-8"))
            alt.attach(MIMEText(body_html, "html", "utf-8"))
            msg.attach(alt)
        elif body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))
        elif body_text:
            msg.attach(MIMEText(body_text, "plain", "utf-8"))

        # Attachments
        for att in attachments:
            part = MIMEBase(*att["content_type"].split("/", 1))
            part.set_payload(att["data"])
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                "attachment",
                filename=att["filename"],
            )
            msg.attach(part)

        return msg

    async def _send_gmail(self, mime_msg: MIMEMultipart) -> Optional[str]:
        """Send via Gmail API."""
        # Encode the message
        raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {self.account.oauth_token}"}

            response = await client.post(
                f"{GMAIL_API}/messages/send",
                headers=headers,
                json={"raw": raw},
            )

            # Token expired — refresh and retry
            if response.status_code == 401:
                await self._refresh_google_token()
                headers = {"Authorization": f"Bearer {self.account.oauth_token}"}
                response = await client.post(
                    f"{GMAIL_API}/messages/send",
                    headers=headers,
                    json={"raw": raw},
                )

            response.raise_for_status()
            data = response.json()
            return data.get("id")

    async def _send_smtp(self, mime_msg: MIMEMultipart) -> Optional[str]:
        """Send via Stalwart SMTP."""
        if not self.account.smtp_host:
            raise ValueError(f"No SMTP host configured for account {self.account.email_address}")
        host = self.account.smtp_host
        port = self.account.smtp_port or 465

        # Collect all recipient addresses
        all_recipients = []
        for header_name in ("To", "Cc", "Bcc"):
            header_val = mime_msg.get(header_name, "")
            if header_val:
                for addr in header_val.split(","):
                    addr = addr.strip()
                    if "<" in addr:
                        addr = addr[addr.index("<") + 1:addr.index(">")]
                    all_recipients.append(addr.strip())

        # Remove Bcc from headers before sending (it shouldn't be visible)
        if "Bcc" in mime_msg:
            del mime_msg["Bcc"]

        from app.services.crypto import decrypt_credential
        await aiosmtplib.send(
            mime_msg,
            hostname=host,
            port=port,
            username=self.account.username,
            password=decrypt_credential(self.account.password),
            use_tls=True,
            sender=self.account.email_address,
            recipients=all_recipients,
        )

        # SMTP doesn't return an ID, use Message-ID header
        return mime_msg.get("Message-ID")

    async def _refresh_google_token(self):
        """Refresh the Google OAuth token."""
        if not self.account.oauth_refresh_token:
            raise Exception(f"No refresh token for {self.account.email_address}")

        token_data = await refresh_google_token(self.account.oauth_refresh_token)
        self.account.oauth_token = token_data["access_token"]
        if "refresh_token" in token_data:
            self.account.oauth_refresh_token = token_data["refresh_token"]
        await self.db.commit()

    async def _append_signature(
        self,
        signature_id: str,
        body_html: Optional[str],
        body_text: Optional[str],
    ) -> tuple[Optional[str], Optional[str]]:
        """Append a signature to the message body."""
        result = await self.db.execute(
            select(Signature).where(
                Signature.id == signature_id,
                Signature.account_id == self.account.id,
            )
        )
        sig = result.scalar_one_or_none()

        if not sig:
            return body_html, body_text

        if body_html and sig.body_html:
            body_html = f"{body_html}<br><br>--<br>{sig.body_html}"
        if body_text and sig.body_text:
            body_text = f"{body_text}\n\n--\n{sig.body_text}"

        return body_html, body_text

    async def _store_sent_message(
        self,
        to: list[dict],
        cc: list[dict],
        bcc: list[dict],
        subject: str,
        body_html: Optional[str],
        body_text: Optional[str],
        in_reply_to: Optional[str],
        references: Optional[str],
        remote_id: Optional[str],
        read_receipt: bool,
        attachments: list[dict] = None,
        tracking_token: Optional[uuid.UUID] = None,
    ) -> Message:
        """Store sent message in the local database."""
        now = datetime.now(timezone.utc)
        attachments = attachments or []

        # Find existing thread or create new one
        thread = None
        if in_reply_to:
            result = await self.db.execute(
                select(Message.thread_id).where(
                    Message.message_id_header == in_reply_to,
                )
            )
            row = result.first()
            if row:
                thread_result = await self.db.execute(
                    select(Thread).where(Thread.id == row[0])
                )
                thread = thread_result.scalar_one_or_none()

        if not thread:
            thread = Thread(
                user_id=self.account.user_id,
                subject=subject,
                last_message_at=now,
                message_count=0,
            )
            self.db.add(thread)
            await self.db.flush()

        snippet = None
        if body_text:
            snippet = body_text[:500].replace("\n", " ").strip()

        message = Message(
            thread_id=thread.id,
            account_id=self.account.id,
            remote_id=remote_id,
            from_address=(self.account.email_address or "").strip().lower(),
            from_name=self.account.display_name,
            to_addresses=to,
            cc_addresses=cc,
            bcc_addresses=bcc,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            snippet=snippet,
            is_read=True,
            is_sent=True,
            is_draft=False,
            has_attachments=len(attachments) > 0,
            read_receipt_requested=read_receipt,
            tracking_token=tracking_token,
            in_reply_to=in_reply_to,
            references=references,
            sent_at=now,
            received_at=now,
        )
        self.db.add(message)
        await self.db.flush()

        await self.db.execute(
            sa_update(Thread)
            .where(Thread.id == thread.id)
            .values(message_count=Thread.message_count + 1, last_message_at=now)
        )

        await self.db.commit()
        await self.db.refresh(message)
        return message


# --- Helpers ---

def _format_address(addr: dict) -> str:
    """Format {"name": "...", "address": "..."} to 'Name <email>'."""
    name = addr.get("name")
    address = addr.get("address", "")
    if name:
        return f"{name} <{address}>"
    return address
