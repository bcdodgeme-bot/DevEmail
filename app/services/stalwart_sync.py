"""
Stalwart Mail Server Sync Service

Connects to Stalwart via IMAP (asyncio) to sync folders
and messages into the local database.
"""

import email
import email.utils
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.folder import Folder
from app.models.thread import Thread
from app.models.message import Message
from app.models.attachment import Attachment
from app.models.unsubscribe import UnsubscribeLink

logger = logging.getLogger(__name__)

# Folder names that indicate sent mail (case-insensitive)
SENT_FOLDER_NAMES = {"sent", "sent items", "sent mail", "sent messages"}


class StalwartSyncService:
    """Handles syncing a single Stalwart mail account via IMAP."""

    def __init__(self, db: AsyncSession, account: Account):
        self.db = db
        self.account = account
        self._imap = None

    async def connect(self):
        """Establish IMAP connection to Stalwart."""
        import aioimaplib

        host = self.account.imap_host or "mail.damnitcarl.dev"
        port = self.account.imap_port or 993

        self._imap = aioimaplib.IMAP4_SSL(host=host, port=port)
        await self._imap.wait_hello_from_server()

        response = await self._imap.login(
            self.account.username,
            self.account.password,
        )

        if response.result != "OK":
            raise Exception(f"IMAP login failed for {self.account.email_address}: {response.lines}")

        logger.info(f"Connected to Stalwart IMAP as {self.account.email_address}")

    async def disconnect(self):
        """Close the IMAP connection."""
        if self._imap:
            try:
                await self._imap.logout()
            except Exception:
                pass
            self._imap = None

    # --- Folder Sync ---

    async def sync_folders(self) -> list[Folder]:
        """Sync IMAP mailbox folders to local folders table."""
        if not self._imap:
            await self.connect()

        response = await self._imap.list("", "*")

        if response.result != "OK":
            raise Exception(f"Failed to list folders: {response.lines}")

        synced = []

        for line in response.lines:
            if not isinstance(line, str) or not line.strip():
                continue

            folder_name = _parse_imap_folder_name(line)
            if not folder_name:
                continue

            # Determine type
            folder_type = "system" if folder_name.upper() in (
                "INBOX", "SENT", "DRAFTS", "TRASH", "JUNK", "SPAM", "ARCHIVE"
            ) else "custom"

            # Check if folder already exists
            result = await self.db.execute(
                select(Folder).where(
                    Folder.account_id == self.account.id,
                    Folder.remote_id == folder_name,
                )
            )
            folder = result.scalar_one_or_none()

            if folder:
                folder.name = folder_name
            else:
                folder = Folder(
                    account_id=self.account.id,
                    name=folder_name,
                    folder_type=folder_type,
                    remote_id=folder_name,
                )
                self.db.add(folder)

            synced.append(folder)

        await self.db.commit()
        logger.info(f"Synced {len(synced)} folders for {self.account.email_address}")
        return synced

    # --- Message Sync ---

    async def sync_messages(self, folder_name: str = "INBOX", max_results: int = 100) -> int:
        """
        Fetch messages from an IMAP folder and store locally.

        Args:
            folder_name: IMAP folder to sync (default: INBOX)
            max_results: Maximum messages to fetch per sync

        Returns:
            Number of new messages synced
        """
        if not self._imap:
            await self.connect()

        # Select the folder
        response = await self._imap.select(folder_name)
        if response.result != "OK":
            raise Exception(f"Failed to select folder {folder_name}: {response.lines}")

        # Get folder_id
        folder_id = await self._resolve_folder_id(folder_name)

        # Search for messages
        if self.account.last_synced_at:
            # Incremental: only messages since last sync
            since_date = self.account.last_synced_at.strftime("%d-%b-%Y")
            search_response = await self._imap.search(f"SINCE {since_date}")
        else:
            # First sync: get most recent messages
            search_response = await self._imap.search("ALL")

        if search_response.result != "OK":
            logger.warning(f"Search failed for {folder_name}: {search_response.lines}")
            return 0

        # Parse message UIDs
        uids = _parse_search_uids(search_response.lines)
        if not uids:
            logger.info(f"No messages found in {folder_name}")
            return 0

        # Limit to most recent
        uids = uids[-max_results:]

        new_count = 0

        for uid in uids:
            # Check if we already have this message
            remote_id = f"{folder_name}:{uid}"
            result = await self.db.execute(
                select(Message).where(
                    Message.account_id == self.account.id,
                    Message.remote_id == remote_id,
                )
            )
            if result.scalar_one_or_none():
                continue

            # Fetch the message
            try:
                msg_data = await self._fetch_message(uid)
                if msg_data:
                    await self._store_message(msg_data, remote_id, folder_id, folder_name)
                    new_count += 1
            except Exception as e:
                logger.error(f"Failed to fetch message UID {uid}: {e}")
                continue

        # Update last synced timestamp
        self.account.last_synced_at = datetime.now(timezone.utc)
        await self.db.commit()

        logger.info(f"Synced {new_count} new messages from {folder_name} for {self.account.email_address}")
        return new_count

    async def sync_all_folders(self, max_per_folder: int = 100) -> int:
        """Sync messages from all folders."""
        folders = await self.sync_folders()
        total = 0

        for folder in folders:
            try:
                count = await self.sync_messages(
                    folder_name=folder.remote_id,
                    max_results=max_per_folder,
                )
                total += count
            except Exception as e:
                logger.error(f"Failed to sync folder {folder.name}: {e}")
                continue

        return total

    async def _fetch_message(self, uid: str) -> Optional[email.message.Message]:
        """Fetch a single message by UID."""
        response = await self._imap.uid("fetch", uid, "(RFC822 FLAGS)")

        if response.result != "OK":
            return None

        # Parse the raw email data from response
        raw_email = None
        flags = set()

        for item in response.lines:
            if isinstance(item, bytes):
                raw_email = item
            elif isinstance(item, str) and "FLAGS" in item:
                flags = _parse_flags(item)

        if not raw_email:
            return None

        msg = email.message_from_bytes(raw_email)
        msg._imap_flags = flags
        return msg

    async def _store_message(
        self,
        msg: email.message.Message,
        remote_id: str,
        folder_id: Optional[str],
        folder_name: str = "",
    ):
        """Parse an email.message.Message and store in database."""
        # Parse headers
        from_raw = msg.get("From", "")
        from_name, from_address = _parse_email_header_address(from_raw)
        to_raw = msg.get("To", "")
        cc_raw = msg.get("Cc", "")
        bcc_raw = msg.get("Bcc", "")
        subject = _decode_header(msg.get("Subject", ""))
        message_id_header = msg.get("Message-ID")
        in_reply_to = msg.get("In-Reply-To")
        references = msg.get("References")
        date_str = msg.get("Date")

        # Parse date
        received_at = None
        if date_str:
            try:
                received_at = email.utils.parsedate_to_datetime(date_str)
            except Exception:
                received_at = datetime.now(timezone.utc)

        # Parse body
        body_html, body_text = _extract_email_body(msg)

        # Snippet from text body
        snippet = None
        if body_text:
            snippet = body_text[:500].replace("\n", " ").strip()

        # Flags
        flags = getattr(msg, "_imap_flags", set())
        is_read = "\\Seen" in flags
        is_starred = "\\Flagged" in flags
        is_draft = "\\Draft" in flags

        # Detect sent folder
        is_sent = folder_name.lower().strip() in SENT_FOLDER_NAMES

        # Check for attachments
        has_attachments = _message_has_attachments(msg)

        # Find or create thread
        thread = await self._resolve_thread(subject, message_id_header, in_reply_to, received_at)

        # Create message
        message = Message(
            thread_id=thread.id,
            account_id=self.account.id,
            folder_id=folder_id,
            remote_id=remote_id,
            message_id_header=message_id_header,
            in_reply_to=in_reply_to,
            references=references,
            from_address=from_address,
            from_name=from_name,
            to_addresses=_parse_header_address_list(to_raw),
            cc_addresses=_parse_header_address_list(cc_raw),
            bcc_addresses=_parse_header_address_list(bcc_raw),
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            snippet=snippet,
            is_read=is_read,
            is_starred=is_starred,
            is_draft=is_draft,
            is_sent=is_sent,
            is_trashed=False,
            has_attachments=has_attachments,
            received_at=received_at,
        )
        self.db.add(message)
        await self.db.flush()

        # Store attachment metadata
        if has_attachments:
            await self._store_attachments(message, msg)

        # Check for unsubscribe header
        unsub = msg.get("List-Unsubscribe")
        if unsub:
            await self._store_unsubscribe(message, unsub, msg.get("List-Id"))

        # Update thread
        thread.message_count += 1
        if not thread.last_message_at or (received_at and received_at > thread.last_message_at):
            thread.last_message_at = received_at
        if is_starred:
            thread.is_starred = True

        await self.db.commit()

    async def _resolve_folder_id(self, folder_name: str) -> Optional[str]:
        """Get local folder ID for an IMAP folder name."""
        result = await self.db.execute(
            select(Folder).where(
                Folder.account_id == self.account.id,
                Folder.remote_id == folder_name,
            )
        )
        folder = result.scalar_one_or_none()
        return folder.id if folder else None

    async def _resolve_thread(self, subject: str, message_id: str, in_reply_to: str, received_at) -> Thread:
        """Find or create a thread for this message."""
        # Try matching by In-Reply-To header
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
                if thread:
                    return thread

        # Try matching by subject
        if subject:
            clean = subject
            for prefix in ("Re: ", "RE: ", "Fwd: ", "FWD: ", "Fw: "):
                while clean.startswith(prefix):
                    clean = clean[len(prefix):]
            clean = clean.strip()

            if clean:
                result = await self.db.execute(
                    select(Thread).where(
                        Thread.user_id == self.account.user_id,
                        Thread.subject == clean,
                    ).order_by(Thread.created_at.desc()).limit(1)
                )
                thread = result.scalar_one_or_none()
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

    async def _store_attachments(self, message: Message, msg: email.message.Message):
        """Extract attachment metadata from email message."""
        for part in msg.walk():
            content_disposition = part.get("Content-Disposition", "")
            if "attachment" in content_disposition or "inline" in content_disposition:
                filename = part.get_filename()
                if filename:
                    filename = _decode_header(filename)
                    attachment = Attachment(
                        message_id=message.id,
                        filename=filename,
                        content_type=part.get_content_type(),
                        size_bytes=len(part.get_payload(decode=True) or b""),
                    )
                    self.db.add(attachment)

    async def _store_unsubscribe(self, message: Message, unsub_header: str, list_id: str = None):
        """Parse List-Unsubscribe header and store."""
        unsub_url = None
        unsub_email = None

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


# --- Helper Functions ---

def _parse_imap_folder_name(line: str) -> Optional[str]:
    """Parse folder name from IMAP LIST response line."""
    # Format: (\\flags) "delimiter" "folder_name"
    try:
        parts = line.rsplit('"', 2)
        if len(parts) >= 2:
            name = parts[-2].strip()
            if name and name != "/":
                return name
        # Try without quotes
        parts = line.split(" ")
        if parts:
            return parts[-1].strip('"')
    except Exception:
        pass
    return None


def _parse_search_uids(lines: list) -> list[str]:
    """Parse UIDs from IMAP SEARCH response."""
    uids = []
    for line in lines:
        if isinstance(line, str):
            parts = line.strip().split()
            for part in parts:
                if part.isdigit():
                    uids.append(part)
        elif isinstance(line, bytes):
            parts = line.decode("utf-8", errors="replace").strip().split()
            for part in parts:
                if part.isdigit():
                    uids.append(part)
    return uids


def _parse_flags(line: str) -> set:
    """Parse FLAGS from IMAP FETCH response."""
    flags = set()
    if "FLAGS" in line:
        start = line.index("(", line.index("FLAGS"))
        end = line.index(")", start)
        flag_str = line[start + 1:end]
        flags = set(flag_str.split())
    return flags


def _parse_email_header_address(raw: str) -> tuple[Optional[str], str]:
    """Parse 'Name <email>' from email header."""
    if not raw:
        return None, ""

    decoded = _decode_header(raw)

    if "<" in decoded and ">" in decoded:
        name = decoded[:decoded.index("<")].strip().strip('"')
        address = decoded[decoded.index("<") + 1:decoded.index(">")].strip()
        return name or None, address

    return None, decoded.strip()


def _parse_header_address_list(raw: str) -> list[dict]:
    """Parse comma-separated email addresses from header."""
    if not raw:
        return []

    decoded = _decode_header(raw)
    results = []

    for part in decoded.split(","):
        part = part.strip()
        if not part:
            continue
        name, address = _parse_email_header_address(part)
        results.append({"name": name, "address": address})

    return results


def _decode_header(value: str) -> str:
    """Decode RFC 2047 encoded header values."""
    if not value:
        return ""
    try:
        decoded_parts = email.header.decode_header(value)
        result = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                result.append(part)
        return " ".join(result)
    except Exception:
        return value


def _extract_email_body(msg: email.message.Message) -> tuple[Optional[str], Optional[str]]:
    """Extract HTML and plain text body from email message."""
    body_html = None
    body_text = None

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = part.get("Content-Disposition", "")

            # Skip attachments
            if "attachment" in disposition:
                continue

            payload = part.get_payload(decode=True)
            if not payload:
                continue

            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")

            if content_type == "text/html" and not body_html:
                body_html = decoded
            elif content_type == "text/plain" and not body_text:
                body_text = decoded
    else:
        content_type = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if content_type == "text/html":
                body_html = decoded
            else:
                body_text = decoded

    return body_html, body_text


def _message_has_attachments(msg: email.message.Message) -> bool:
    """Check if an email message has attachments."""
    if not msg.is_multipart():
        return False

    for part in msg.walk():
        disposition = part.get("Content-Disposition", "")
        if "attachment" in disposition:
            return True
        if part.get_filename():
            return True

    return False
