"""
Gmail Sync Service

Connects to Gmail API using OAuth tokens, syncs labels/folders
and messages into the local database. Handles token auto-refresh.
"""

import base64
import email
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.folder import Folder
from app.models.thread import Thread
from app.models.message import Message
from app.models.attachment import Attachment
from app.models.unsubscribe import UnsubscribeLink
from app.services.google_oauth import refresh_google_token

logger = logging.getLogger(__name__)

# Gmail API base URL
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailSyncService:
    """Handles syncing a single Gmail account."""

    def __init__(self, db: AsyncSession, account: Account):
        self.db = db
        self.account = account
        self.access_token = account.oauth_token
        self._http = None

    async def _get_http(self):
        """Lazy-init httpx client."""
        if self._http is None:
            import httpx
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    async def _close(self):
        """Close the HTTP client."""
        if self._http:
            await self._http.aclose()
            self._http = None

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        """Make an authenticated Gmail API request with auto-refresh."""
        http = await self._get_http()
        headers = {"Authorization": f"Bearer {self.access_token}"}

        response = await http.request(method, url, headers=headers, **kwargs)

        # Token expired — refresh and retry
        if response.status_code == 401:
            await self._refresh_token()
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = await http.request(method, url, headers=headers, **kwargs)

        response.raise_for_status()
        return response.json()

    async def _refresh_token(self):
        """Refresh the Google access token and update the account record."""
        if not self.account.oauth_refresh_token:
            raise Exception(f"No refresh token for account {self.account.email_address}")

        token_data = await refresh_google_token(self.account.oauth_refresh_token)
        self.access_token = token_data["access_token"]

        # Persist new access token
        self.account.oauth_token = self.access_token
        # Google sometimes issues a new refresh token too
        if "refresh_token" in token_data:
            self.account.oauth_refresh_token = token_data["refresh_token"]
        await self.db.commit()

        logger.info(f"Refreshed Google token for {self.account.email_address}")

    # --- Label / Folder Sync ---

    async def sync_labels(self) -> list[Folder]:
        """Sync Gmail labels to local folders table."""
        data = await self._request("GET", f"{GMAIL_API}/labels")
        labels = data.get("labels", [])
        synced = []

        for label in labels:
            label_id = label["id"]
            label_name = label["name"]
            label_type = "system" if label.get("type") == "system" else "custom"

            # Check if folder already exists for this label
            result = await self.db.execute(
                select(Folder).where(
                    Folder.account_id == self.account.id,
                    Folder.remote_id == label_id,
                )
            )
            folder = result.scalar_one_or_none()

            if folder:
                folder.name = label_name
            else:
                folder = Folder(
                    account_id=self.account.id,
                    name=label_name,
                    folder_type=label_type,
                    remote_id=label_id,
                )
                self.db.add(folder)

            synced.append(folder)

        await self.db.commit()
        logger.info(f"Synced {len(synced)} labels for {self.account.email_address}")
        return synced

    # --- Message Sync ---

    async def sync_messages(self, max_results: int = 500, query: str = None) -> int:
        """
        Fetch messages from Gmail and store locally.

        Args:
            max_results: Maximum messages to fetch per sync
            query: Optional Gmail search query (e.g. 'is:unread', 'after:2024/01/01')

        Returns:
            Number of new messages synced
        """
        # Get message ID list from Gmail (with pagination)
        all_message_refs = []
        page_token = None
        remaining = max_results

        while remaining > 0:
            params = {"maxResults": min(remaining, 100)}
            if query:
                params["q"] = query
            if page_token:
                params["pageToken"] = page_token

            data = await self._request("GET", f"{GMAIL_API}/messages", params=params)
            message_refs = data.get("messages", [])
            all_message_refs.extend(message_refs)
            remaining -= len(message_refs)

            page_token = data.get("nextPageToken")
            if not page_token or not message_refs:
                break

        if not all_message_refs:
            logger.info(f"No new messages for {self.account.email_address}")
            return 0

        new_count = 0

        for ref in all_message_refs:
            gmail_id = ref["id"]

            # Fetch and store — rely on unique constraint to prevent duplicates
            try:
                msg_data = await self._fetch_message(gmail_id)
                if msg_data:
                    await self._store_message(msg_data)
                    new_count += 1
            except IntegrityError:
                await self.db.rollback()
                logger.debug(f"Skipping duplicate message {gmail_id} (already exists)")
            except Exception as e:
                logger.error(f"Failed to fetch message {gmail_id}: {e}")
                continue

        # Update last synced timestamp
        self.account.last_synced_at = datetime.now(timezone.utc)
        await self.db.commit()

        logger.info(f"Synced {new_count} new messages for {self.account.email_address}")
        return new_count

    async def sync_incremental(self) -> int:
        """
        Incremental sync — only fetch messages since last sync.
        Uses Gmail's 'after' query based on last_synced_at.
        """
        query = None
        if self.account.last_synced_at:
            # Gmail accepts epoch seconds for after: query
            epoch = int(self.account.last_synced_at.timestamp())
            query = f"after:{epoch}"

        return await self.sync_messages(query=query)

    async def _fetch_message(self, gmail_id: str) -> Optional[dict]:
        """Fetch a single message with full content from Gmail API."""
        data = await self._request(
            "GET",
            f"{GMAIL_API}/messages/{gmail_id}",
            params={"format": "full"},
        )
        return data

    async def _store_message(self, msg_data: dict):
        """Parse Gmail API message and store in database."""
        gmail_id = msg_data["id"]
        gmail_thread_id = msg_data.get("threadId")
        label_ids = msg_data.get("labelIds", [])

        # Parse headers
        headers = {}
        payload = msg_data.get("payload", {})
        for header in payload.get("headers", []):
            name = header["name"].lower()
            headers[name] = header["value"]

        from_raw = headers.get("from", "")
        from_name, from_address = _parse_email_address(from_raw)
        to_raw = headers.get("to", "")
        cc_raw = headers.get("cc", "")
        bcc_raw = headers.get("bcc", "")
        subject = headers.get("subject", "")
        message_id_header = headers.get("message-id")
        in_reply_to = headers.get("in-reply-to")
        references = headers.get("references")
        date_str = headers.get("date")

        # Parse date
        received_at = None
        if date_str:
            try:
                received_at = email.utils.parsedate_to_datetime(date_str)
            except Exception:
                received_at = datetime.now(timezone.utc)

        # Parse body
        body_html, body_text = _extract_body(payload)

        # Build snippet
        snippet = msg_data.get("snippet", "")

        # Determine flags from labels
        is_read = "UNREAD" not in label_ids
        is_starred = "STARRED" in label_ids
        is_draft = "DRAFT" in label_ids
        is_sent = "SENT" in label_ids
        is_trashed = "TRASH" in label_ids

        # Find or create local folder based on primary label
        folder_id = await self._resolve_folder(label_ids)

        # Find or create thread
        thread = await self._resolve_thread(gmail_thread_id, subject, received_at)

        # Check for attachments
        has_attachments = _has_attachments(payload)

        # Create message
        message = Message(
            thread_id=thread.id,
            account_id=self.account.id,
            folder_id=folder_id,
            remote_id=gmail_id,
            remote_thread_id=gmail_thread_id,
            message_id_header=message_id_header,
            in_reply_to=in_reply_to,
            references=references,
            from_address=from_address,
            from_name=from_name,
            to_addresses=_parse_address_list(to_raw),
            cc_addresses=_parse_address_list(cc_raw),
            bcc_addresses=_parse_address_list(bcc_raw),
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            snippet=snippet[:500] if snippet else None,
            is_read=is_read,
            is_starred=is_starred,
            is_draft=is_draft,
            is_sent=is_sent,
            is_trashed=is_trashed,
            has_attachments=has_attachments,
            received_at=received_at,
            sent_at=received_at if is_sent else None,
        )
        self.db.add(message)
        await self.db.flush()

        # Store attachment metadata (not downloading content yet)
        if has_attachments:
            await self._store_attachment_metadata(message, payload)

        # Update thread atomically
        from sqlalchemy import func as sqlfunc
        await self.db.execute(
            update(Thread)
            .where(Thread.id == thread.id)
            .values(message_count=Thread.message_count + 1)
        )
        if not thread.last_message_at or (received_at and received_at > thread.last_message_at):
            thread.last_message_at = received_at
        if is_starred:
            thread.is_starred = True

        # Commit the message, attachments, and thread update first
        await self.db.commit()

        # Check for unsubscribe header (non-fatal — don't let this kill the sync)
        unsub = headers.get("list-unsubscribe")
        if unsub:
            try:
                await self._store_unsubscribe(message, unsub, headers.get("list-id"))
                await self.db.commit()
            except Exception as e:
                logger.warning(f"Failed to store unsubscribe link for {gmail_id}: {e}")
                await self.db.rollback()

    async def _resolve_folder(self, label_ids: list[str]) -> Optional[str]:
        """Map Gmail label IDs to a local folder ID."""
        # Priority: INBOX > SENT > DRAFT > TRASH > SPAM > first custom label
        priority = ["INBOX", "SENT", "DRAFT", "TRASH", "SPAM"]

        target_label = None
        for p in priority:
            if p in label_ids:
                target_label = p
                break

        if not target_label:
            # Use first non-system label
            custom = [l for l in label_ids if not l.startswith("CATEGORY_") and l not in ("UNREAD", "STARRED", "IMPORTANT")]
            if custom:
                target_label = custom[0]

        if not target_label:
            return None

        result = await self.db.execute(
            select(Folder).where(
                Folder.account_id == self.account.id,
                Folder.remote_id == target_label,
            )
        )
        folder = result.scalar_one_or_none()
        return folder.id if folder else None

    async def _resolve_thread(self, gmail_thread_id: str, subject: str, received_at) -> Thread:
        """Find or create a local thread for a Gmail thread ID."""
        # First: look for existing messages from the same Gmail thread
        # Gmail groups messages by threadId, so if we already have a message
        # from this Gmail thread, reuse that local thread
        if gmail_thread_id:
            result = await self.db.execute(
                select(Message).where(
                    Message.account_id == self.account.id,
                    Message.remote_thread_id == gmail_thread_id,
                ).limit(1)
            )
            existing_msg = result.scalar_one_or_none()
            if existing_msg:
                thread_result = await self.db.execute(
                    select(Thread).where(Thread.id == existing_msg.thread_id)
                )
                thread = thread_result.scalar_one_or_none()
                if thread:
                    return thread

        # Create new thread
        thread = Thread(
            user_id=self.account.user_id,
            subject=subject,
            last_message_at=received_at,
            message_count=0,
        )
        self.db.add(thread)
        await self.db.flush()
        return thread

    async def _store_attachment_metadata(self, message: Message, payload: dict):
        """Store attachment metadata from message parts."""
        parts = payload.get("parts", [])
        for part in parts:
            filename = part.get("filename")
            if filename:
                attachment = Attachment(
                    message_id=message.id,
                    filename=filename,
                    content_type=part.get("mimeType"),
                    size_bytes=int(part.get("body", {}).get("size", 0)),
                    remote_id=part.get("body", {}).get("attachmentId"),
                )
                self.db.add(attachment)

            # Recurse into nested parts
            if "parts" in part:
                for sub in part["parts"]:
                    fname = sub.get("filename")
                    if fname:
                        attachment = Attachment(
                            message_id=message.id,
                            filename=fname,
                            content_type=sub.get("mimeType"),
                            size_bytes=int(sub.get("body", {}).get("size", 0)),
                            remote_id=sub.get("body", {}).get("attachmentId"),
                        )
                        self.db.add(attachment)

    async def _store_unsubscribe(self, message: Message, unsub_header: str, list_id: str = None):
        """Parse List-Unsubscribe header and store."""
        unsub_url = None
        unsub_email = None

        # Header can contain <url>, <mailto:email>, or both
        parts = unsub_header.split(",")
        for part in parts:
            part = part.strip().strip("<>")
            if part.startswith("mailto:"):
                unsub_email = part.replace("mailto:", "")
            elif part.startswith("http"):
                unsub_url = part

        if unsub_url or unsub_email:
            link = UnsubscribeLink(
                message_id=message.id,
                unsubscribe_url=unsub_url,
                unsubscribe_email=unsub_email,
                list_id=list_id,
            )
            self.db.add(link)

    async def fetch_attachment_content(self, attachment_remote_id: str) -> bytes:
        """Download attachment content from Gmail API."""
        # Find the message this attachment belongs to
        result = await self.db.execute(
            select(Attachment).where(Attachment.remote_id == attachment_remote_id)
        )
        att = result.scalar_one_or_none()
        if not att:
            raise Exception("Attachment not found")

        # Get the message's remote ID
        msg_result = await self.db.execute(
            select(Message.remote_id).where(Message.id == att.message_id)
        )
        msg_remote_id = msg_result.scalar_one()

        data = await self._request(
            "GET",
            f"{GMAIL_API}/messages/{msg_remote_id}/attachments/{attachment_remote_id}",
        )

        # Gmail returns base64url encoded data
        raw = data.get("data", "")
        return base64.urlsafe_b64decode(raw)


# --- Helper Functions ---

def _parse_email_address(raw: str) -> tuple[Optional[str], str]:
    """Parse 'Name <email@example.com>' into (name, address)."""
    if not raw:
        return None, ""

    if "<" in raw and ">" in raw:
        name = raw[:raw.index("<")].strip().strip('"')
        address = raw[raw.index("<") + 1:raw.index(">")].strip()
        return name or None, address

    return None, raw.strip()


def _parse_address_list(raw: str) -> list[dict]:
    """Parse comma-separated email addresses into list of {name, address}."""
    if not raw:
        return []

    results = []
    # Simple split — won't handle commas inside quoted names perfectly
    # but covers the vast majority of cases
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        name, address = _parse_email_address(part)
        results.append({"name": name, "address": address})

    return results


def _extract_body(payload: dict) -> tuple[Optional[str], Optional[str]]:
    """Extract HTML and plain text body from Gmail message payload."""
    body_html = None
    body_text = None

    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")

    if body_data:
        decoded = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
        if "html" in mime_type:
            body_html = decoded
        else:
            body_text = decoded

    # Recurse into multipart
    parts = payload.get("parts", [])
    for part in parts:
        part_mime = part.get("mimeType", "")
        part_data = part.get("body", {}).get("data")

        if part_data:
            decoded = base64.urlsafe_b64decode(part_data).decode("utf-8", errors="replace")
            if "html" in part_mime and not body_html:
                body_html = decoded
            elif "plain" in part_mime and not body_text:
                body_text = decoded

        # Handle nested multipart
        if "parts" in part:
            sub_html, sub_text = _extract_body(part)
            if sub_html and not body_html:
                body_html = sub_html
            if sub_text and not body_text:
                body_text = sub_text

    return body_html, body_text


def _has_attachments(payload: dict) -> bool:
    """Check if a message payload contains attachments."""
    parts = payload.get("parts", [])
    for part in parts:
        if part.get("filename"):
            return True
        if "parts" in part:
            if _has_attachments(part):
                return True
    return False
