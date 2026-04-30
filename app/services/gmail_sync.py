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

from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.folder import Folder
from app.models.thread import Thread
from app.models.message import Message
from app.models.attachment import Attachment
from app.models.unsubscribe import UnsubscribeLink
from app.services.classification import ClassificationBatch
from app.services.google_oauth import refresh_google_token

logger = logging.getLogger(__name__)

# Gmail API base URL
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailSyncService:
    """Handles syncing a single Gmail account."""

    def __init__(self, db: AsyncSession, account: Account):
        self.db = db
        self.account = account
        # Snapshot account fields as plain Python so we never read expired
        # ORM attributes from within synchronous code paths (e.g. while
        # constructing select()/Model(...) expressions). After any rollback
        # on the shared session, ORM attributes on `self.account` are
        # expired and reading them would trigger an implicit lazy refresh
        # — which is async I/O invoked from sync code and raises
        # greenlet_spawn. Plain attributes are immune.
        self._account_id = account.id
        self._user_id = account.user_id
        self._email = account.email_address
        self.access_token = account.oauth_token
        self._http = None
        # One classifier batch per service instance (= per sync run).
        # Caches sender-stable results across all messages this run inserts.
        self._classifier = ClassificationBatch(db, self._account_id, self._user_id)

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
        # 204 No Content (e.g. batchModify on success) has no body to decode.
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    async def _refresh_token(self):
        """Refresh the Google access token and update the account record."""
        # Re-attach: if the shared session was rolled back, self.account is
        # expired. Refresh it before reading oauth_refresh_token in sync code.
        await self.db.refresh(self.account)

        if not self.account.oauth_refresh_token:
            raise Exception(f"No refresh token for account {self._email}")

        token_data = await refresh_google_token(self.account.oauth_refresh_token)
        self.access_token = token_data["access_token"]

        # Persist new access token
        self.account.oauth_token = self.access_token
        # Google sometimes issues a new refresh token too
        if "refresh_token" in token_data:
            self.account.oauth_refresh_token = token_data["refresh_token"]
        await self.db.commit()

        logger.info(f"Refreshed Google token for {self._email}")

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
                    Folder.account_id == self._account_id,
                    Folder.remote_id == label_id,
                )
            )
            folder = result.scalar_one_or_none()

            if folder:
                folder.name = label_name
            else:
                folder = Folder(
                    account_id=self._account_id,
                    name=label_name,
                    folder_type=label_type,
                    remote_id=label_id,
                )
                self.db.add(folder)

            synced.append(folder)

        await self.db.commit()
        logger.info(f"Synced {len(synced)} labels for {self._email}")
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
            logger.info(f"No new messages for {self._email}")
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

        # Update last synced timestamp via SQL UPDATE — avoids reading or
        # mutating expired ORM attributes on self.account.
        await self.db.execute(
            update(Account)
            .where(Account.id == self._account_id)
            .values(last_synced_at=datetime.now(timezone.utc))
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()

        logger.info(f"Synced {new_count} new messages for {self._email}")
        return new_count

    async def sync_incremental(self) -> int:
        """
        Incremental sync.

        If gmail_history_id is set, use history.list to detect:
          - new messages (messagesAdded)
          - remote archives (INBOX label removed)
          - remote trashes (TRASH label added) and deletes (messagesDeleted)
          - un-archives (INBOX label added back)

        Otherwise fall back to the older after:<epoch> query and seed the
        gmail_history_id from the most recent message for next time.
        """
        # Read account state via direct SELECT — never via expired ORM attrs.
        row = (await self.db.execute(
            select(Account.gmail_history_id, Account.last_synced_at)
            .where(Account.id == self._account_id)
        )).one()
        gmail_history_id, last_synced_at = row

        if gmail_history_id:
            try:
                return await self._sync_via_history(gmail_history_id)
            except Exception as e:
                # 404 = historyId too old (> ~7 days). Full resync below.
                logger.warning(
                    "history.list failed for %s (%s) — falling back to full incremental",
                    self._email, e,
                )
                await self.db.execute(
                    update(Account)
                    .where(Account.id == self._account_id)
                    .values(gmail_history_id=None)
                    .execution_options(synchronize_session=False)
                )
                await self.db.commit()

        # Legacy / first-run path
        query = None
        if last_synced_at:
            epoch = int(last_synced_at.timestamp())
            query = f"after:{epoch}"

        new_count = await self.sync_messages(query=query)
        await self._seed_history_id()
        return new_count

    async def _seed_history_id(self):
        """Record the current Gmail profile historyId so future syncs use history.list."""
        try:
            data = await self._request("GET", f"{GMAIL_API}/profile")
            hid = data.get("historyId")
            if hid:
                await self.db.execute(
                    update(Account)
                    .where(Account.id == self._account_id)
                    .values(gmail_history_id=str(hid))
                    .execution_options(synchronize_session=False)
                )
                await self.db.commit()
        except Exception as e:
            logger.warning("Failed to seed gmail_history_id for %s: %s", self._email, e)

    async def _sync_via_history(self, start_id: str) -> int:
        """Apply Gmail history records since gmail_history_id."""
        page_token = None
        new_count = 0
        latest_history_id = start_id

        # Collect changes across pages before applying, so we batch updates
        added_ids: set[str] = set()
        label_changes: dict[str, dict[str, set[str]]] = {}  # remote_id -> {'added': {labels}, 'removed': {labels}}
        deleted_ids: set[str] = set()

        while True:
            params = {
                "startHistoryId": start_id,
                "historyTypes": ["messageAdded", "labelAdded", "labelRemoved", "messageDeleted"],
            }
            if page_token:
                params["pageToken"] = page_token

            data = await self._request("GET", f"{GMAIL_API}/history", params=params)
            records = data.get("history", [])
            if data.get("historyId"):
                latest_history_id = str(data["historyId"])

            for rec in records:
                for m in rec.get("messagesAdded", []):
                    mid = m.get("message", {}).get("id")
                    if mid:
                        added_ids.add(mid)
                for m in rec.get("messagesDeleted", []):
                    mid = m.get("message", {}).get("id")
                    if mid:
                        deleted_ids.add(mid)
                for la in rec.get("labelsAdded", []):
                    mid = la.get("message", {}).get("id")
                    labels = la.get("labelIds", [])
                    if mid and labels:
                        entry = label_changes.setdefault(mid, {"added": set(), "removed": set()})
                        entry["added"].update(labels)
                for lr in rec.get("labelsRemoved", []):
                    mid = lr.get("message", {}).get("id")
                    labels = lr.get("labelIds", [])
                    if mid and labels:
                        entry = label_changes.setdefault(mid, {"added": set(), "removed": set()})
                        entry["removed"].update(labels)

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        # Apply new messages
        for gmail_id in added_ids:
            try:
                msg_data = await self._fetch_message(gmail_id)
                if msg_data:
                    await self._store_message(msg_data)
                    new_count += 1
            except IntegrityError:
                await self.db.rollback()
            except Exception as e:
                await self.db.rollback()
                logger.error("history messagesAdded: failed to store %s: %s", gmail_id, e)

        # Apply label changes to existing messages
        for remote_id, changes in label_changes.items():
            added = changes["added"]
            removed = changes["removed"]
            values = {}
            if "TRASH" in added:
                values["is_trashed"] = True
            if "TRASH" in removed:
                values["is_trashed"] = False
            if "INBOX" in removed:
                values["is_archived"] = True
            if "INBOX" in added:
                values["is_archived"] = False
            if "UNREAD" in removed:
                values["is_read"] = True
            if "UNREAD" in added:
                values["is_read"] = False
            if "STARRED" in added:
                values["is_starred"] = True
            if "STARRED" in removed:
                values["is_starred"] = False
            if values:
                await self.db.execute(
                    update(Message)
                    .where(
                        Message.account_id == self._account_id,
                        Message.remote_id == remote_id,
                    )
                    .values(**values)
                )

        # Apply hard deletes → mark trashed locally
        if deleted_ids:
            await self.db.execute(
                update(Message)
                .where(
                    Message.account_id == self._account_id,
                    Message.remote_id.in_(list(deleted_ids)),
                )
                .values(is_trashed=True)
            )

        # Advance pointer via SQL UPDATE — never touch the (possibly expired)
        # self.account ORM instance.
        account_values = {"last_synced_at": datetime.now(timezone.utc)}
        if latest_history_id:
            account_values["gmail_history_id"] = latest_history_id
        await self.db.execute(
            update(Account)
            .where(Account.id == self._account_id)
            .values(**account_values)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()

        logger.info(
            "History sync %s: new=%d labeled=%d deleted=%d",
            self._email, new_count, len(label_changes), len(deleted_ids),
        )
        return new_count

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

        # Find or create thread — returns ID only. We never hold a Thread ORM
        # instance across awaits/commits, so an expired-attribute lazy refresh
        # cannot be triggered from sync code.
        thread_id = await self._resolve_thread(gmail_thread_id, subject, received_at)

        # Check for attachments
        has_attachments = _has_attachments(payload)

        # Classify People / Bulk before INSERT so category lands on the row
        # immediately. Sent mail bypasses classification — the schema default
        # ('people', 'default') applies and sent items live in their own view.
        if is_sent:
            category, category_source = "people", "default"
        else:
            category, category_source = await self._classifier.classify(
                from_address=from_address,
                headers=headers,
                content_type=headers.get("content-type"),
                remote_id=gmail_id,
            )

        # Create message
        message = Message(
            thread_id=thread_id,
            account_id=self._account_id,
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
            category=category,
            category_source=category_source,
        )
        self.db.add(message)
        await self.db.flush()

        # Store attachment metadata (not downloading content yet)
        if has_attachments:
            await self._store_attachment_metadata(message, payload)

        # Update thread atomically with a single SQL UPDATE. We never read or
        # mutate a Thread ORM instance — all changes are pure SQL expressions,
        # so there is no in-session ORM state to be expired and no chance of
        # an implicit lazy refresh raising greenlet_spawn.
        thread_values = {
            "message_count": Thread.message_count + 1,
        }
        if received_at is not None:
            # GREATEST(last_message_at, received_at), NULL-safe via COALESCE.
            thread_values["last_message_at"] = func.greatest(
                func.coalesce(Thread.last_message_at, received_at),
                received_at,
            )
        if is_starred:
            # is_starred OR TRUE  →  TRUE; preserves existing TRUE otherwise.
            thread_values["is_starred"] = True
        await self.db.execute(
            update(Thread)
            .where(Thread.id == thread_id)
            .values(**thread_values)
            .execution_options(synchronize_session=False)
        )

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

        # Select only the ID column — avoids loading Folder ORM (and its
        # selectin relationships), and avoids returning a session-attached
        # ORM instance that could expire.
        result = await self.db.execute(
            select(Folder.id).where(
                Folder.account_id == self._account_id,
                Folder.remote_id == target_label,
            )
        )
        return result.scalar_one_or_none()

    async def _resolve_thread(self, gmail_thread_id: str, subject: str, received_at):
        """Find or create a local thread. Returns the thread's UUID, never an
        ORM instance — keeps _store_message free of Thread ORM mutations."""
        # First: look for existing messages from the same Gmail thread.
        # Gmail groups messages by threadId, so if we already have a message
        # from this Gmail thread, reuse that local thread.
        if gmail_thread_id:
            result = await self.db.execute(
                select(Message.thread_id).where(
                    Message.account_id == self._account_id,
                    Message.remote_thread_id == gmail_thread_id,
                ).limit(1)
            )
            existing_thread_id = result.scalar_one_or_none()
            if existing_thread_id is not None:
                return existing_thread_id

        # Create new thread
        thread = Thread(
            user_id=self._user_id,
            subject=subject,
            last_message_at=received_at,
            message_count=0,
        )
        self.db.add(thread)
        await self.db.flush()
        new_id = thread.id
        # Drop the ORM reference: we don't want to hold a Thread instance
        # that could be expired by a later rollback in the same session.
        return new_id

    async def _store_attachment_metadata(self, message: Message, payload: dict):
        """Store attachment metadata from message parts, including inline images
        (parts with a Content-ID header, typically referenced via cid: URLs)."""
        def walk(parts: list[dict]):
            for part in parts:
                filename = part.get("filename")
                headers = {
                    (h.get("name") or "").lower(): h.get("value", "")
                    for h in part.get("headers", [])
                }
                content_id = headers.get("content-id", "").strip().strip("<>")
                disposition = headers.get("content-disposition", "").lower()
                mime = part.get("mimeType", "") or ""
                attachment_id = part.get("body", {}).get("attachmentId")

                is_inline = bool(
                    content_id
                    and attachment_id
                    and (mime.startswith("image/") or "inline" in disposition)
                )
                has_file = bool(filename) and bool(attachment_id)

                if has_file or is_inline:
                    self.db.add(Attachment(
                        message_id=message.id,
                        filename=filename or content_id or "inline",
                        content_type=mime or None,
                        size_bytes=int(part.get("body", {}).get("size", 0) or 0),
                        remote_id=attachment_id,
                        content_id=content_id or None,
                        is_inline=is_inline,
                    ))

                if "parts" in part:
                    walk(part["parts"])

        walk(payload.get("parts", []))

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

    async def batch_modify_labels(
        self,
        remote_ids: list[str],
        add_labels: list[str] = None,
        remove_labels: list[str] = None,
    ) -> None:
        """Apply label changes to a batch of Gmail messages via batchModify."""
        remote_ids = [r for r in (remote_ids or []) if r]
        if not remote_ids:
            return
        payload = {"ids": remote_ids}
        if add_labels:
            payload["addLabelIds"] = add_labels
        if remove_labels:
            payload["removeLabelIds"] = remove_labels
        await self._request(
            "POST",
            f"{GMAIL_API}/messages/batchModify",
            json=payload,
        )

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
    """Check if a message payload contains a non-inline attachment. Inline
    images (Content-Disposition: inline, referenced via cid:) don't count."""
    parts = payload.get("parts", [])
    for part in parts:
        if part.get("filename"):
            headers = {
                (h.get("name") or "").lower(): h.get("value", "")
                for h in part.get("headers", [])
            }
            disposition = headers.get("content-disposition", "").lower()
            if "inline" not in disposition:
                return True
        if "parts" in part:
            if _has_attachments(part):
                return True
    return False
