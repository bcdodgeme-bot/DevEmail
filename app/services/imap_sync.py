"""
IMAP Sync Service — fetch emails from a Stalwart (or any IMAP) mailbox
and write them into the threads + messages tables.

Uses stdlib imaplib wrapped in asyncio.to_thread for async compatibility.
"""

import asyncio
import email
import imaplib
import logging
import uuid
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.thread import Thread
from app.models.message import Message

logger = logging.getLogger(__name__)


# ── Header decoding helpers ────────────────────────────

def decode_mime_header(value: str) -> str:
    """Decode a MIME-encoded header value into a plain string."""
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded).strip()


def parse_address(raw: str) -> dict:
    """Parse 'Name <email>' into {name, address}."""
    name, addr = parseaddr(raw)
    return {"name": decode_mime_header(name), "address": addr}


def parse_address_list(raw: str) -> list[dict]:
    """Parse a comma-separated address list."""
    if not raw:
        return []
    # Split on commas, but be careful of commas inside quoted names
    addresses = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            addresses.append(parse_address(part))
    return addresses


def parse_date(msg: email.message.Message) -> Optional[datetime]:
    """Extract and parse the Date header."""
    date_str = msg.get("Date")
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def get_body(msg: email.message.Message) -> tuple[Optional[str], Optional[str]]:
    """Extract body_html and body_text from an email message."""
    body_html = None
    body_text = None

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))

            # Skip attachments
            if "attachment" in disposition:
                continue

            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
            except Exception:
                continue

            if content_type == "text/html" and not body_html:
                body_html = decoded
            elif content_type == "text/plain" and not body_text:
                body_text = decoded
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    body_html = decoded
                else:
                    body_text = decoded
        except Exception:
            pass

    return body_html, body_text


def make_snippet(body_text: Optional[str], body_html: Optional[str], max_len: int = 200) -> str:
    """Create a short preview snippet from the body."""
    source = body_text or ""
    if not source and body_html:
        # Rough strip of HTML tags
        import re
        source = re.sub(r"<[^>]+>", " ", body_html)
        source = re.sub(r"\s+", " ", source).strip()
    return source[:max_len] if source else ""


def count_attachments(msg: email.message.Message) -> int:
    """Count attachments in the message."""
    count = 0
    if msg.is_multipart():
        for part in msg.walk():
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                count += 1
    return count


# ── IMAP fetching (synchronous, runs in thread) ───────

def _imap_fetch_all(host: str, port: int, username: str, password: str, folder: str = "INBOX") -> list[bytes]:
    """Connect to IMAP and fetch all messages as raw bytes. Runs synchronously."""
    logger.info(f"Connecting to IMAP {host}:{port} as {username}")
    
    mail = imaplib.IMAP4_SSL(host, port)
    mail.login(username, password)
    mail.select(folder, readonly=True)

    # Search for all messages
    status, data = mail.search(None, "ALL")
    if status != "OK" or not data[0]:
        logger.info("No messages found in mailbox")
        mail.logout()
        return []

    message_nums = data[0].split()
    logger.info(f"Found {len(message_nums)} messages in {folder}")

    raw_messages = []
    for num in message_nums:
        status, msg_data = mail.fetch(num, "(UID RFC822)")
        if status == "OK" and msg_data[0] is not None:
            # msg_data[0] is a tuple: (b'UID RFC822 response', raw_email_bytes)
            if isinstance(msg_data[0], tuple):
                uid_line = msg_data[0][0].decode("utf-8", errors="replace")
                raw_email = msg_data[0][1]
                # Extract UID from response line like b'1 (UID 5 RFC822 {1234}'
                uid = None
                if b"UID" in msg_data[0][0]:
                    parts = uid_line.split()
                    for i, p in enumerate(parts):
                        if p.upper() == "UID" and i + 1 < len(parts):
                            uid = parts[i + 1].rstrip(")")
                            break
                raw_messages.append((uid, raw_email))

    mail.logout()
    return raw_messages


# ── Main sync function ─────────────────────────────────

async def sync_account(account: Account, user_id: uuid.UUID, db: AsyncSession) -> dict:
    """
    Sync a single IMAP account:
    1. Fetch all messages from IMAP
    2. Skip any already imported (by remote_id / message_id_header)
    3. Group into threads by subject + in-reply-to
    4. Create Thread + Message records
    
    Returns a summary dict.
    """
    if not account.imap_host or not account.username or not account.password:
        return {"error": "Account missing IMAP credentials"}

    # Fetch raw messages in a background thread
    try:
        raw_messages = await asyncio.to_thread(
            _imap_fetch_all,
            account.imap_host,
            account.imap_port or 993,
            account.username,
            account.password,
        )
    except Exception as e:
        logger.error(f"IMAP fetch failed for {account.email_address}: {e}")
        return {"error": f"IMAP connection failed: {str(e)}"}

    if not raw_messages:
        return {"fetched": 0, "new": 0, "skipped": 0}

    # Get existing message_id_headers to avoid duplicates
    existing_result = await db.execute(
        select(Message.message_id_header).where(
            Message.account_id == account.id,
            Message.message_id_header.isnot(None),
        )
    )
    existing_msg_ids = set(row[0] for row in existing_result.all())

    # Get existing remote_ids
    existing_remote_result = await db.execute(
        select(Message.remote_id).where(
            Message.account_id == account.id,
            Message.remote_id.isnot(None),
        )
    )
    existing_remote_ids = set(row[0] for row in existing_remote_result.all())

    new_count = 0
    skipped_count = 0

    for uid, raw_email in raw_messages:
        # Parse the email
        msg = email.message_from_bytes(raw_email)

        message_id = msg.get("Message-ID", "").strip()
        remote_id = f"stalwart:{uid}" if uid else None

        # Skip duplicates
        if message_id and message_id in existing_msg_ids:
            skipped_count += 1
            continue
        if remote_id and remote_id in existing_remote_ids:
            skipped_count += 1
            continue

        # Parse headers
        subject = decode_mime_header(msg.get("Subject", ""))
        from_parsed = parse_address(msg.get("From", ""))
        to_list = parse_address_list(msg.get("To", ""))
        cc_list = parse_address_list(msg.get("Cc", ""))
        in_reply_to = msg.get("In-Reply-To", "").strip() or None
        references_header = msg.get("References", "").strip() or None
        date = parse_date(msg)

        # Get body
        body_html, body_text = get_body(msg)
        snippet = make_snippet(body_text, body_html)
        attachment_count = count_attachments(msg)

        # Find or create thread
        thread = await _find_or_create_thread(
            db=db,
            user_id=user_id,
            subject=subject,
            message_id=message_id,
            in_reply_to=in_reply_to,
            references=references_header,
            date=date,
        )

        # Create message
        new_message = Message(
            thread_id=thread.id,
            account_id=account.id,
            remote_id=remote_id,
            message_id_header=message_id or None,
            in_reply_to=in_reply_to,
            references=references_header,
            from_address=from_parsed["address"],
            from_name=from_parsed["name"],
            to_addresses=to_list,
            cc_addresses=cc_list,
            bcc_addresses=[],
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            snippet=snippet,
            is_read=False,
            has_attachments=attachment_count > 0,
            received_at=date,
        )
        db.add(new_message)

        # Update thread
        thread.message_count += 1
        if date and (thread.last_message_at is None or date > thread.last_message_at):
            thread.last_message_at = date

        # Track to avoid duplicates within this batch
        if message_id:
            existing_msg_ids.add(message_id)
        if remote_id:
            existing_remote_ids.add(remote_id)

        new_count += 1

    # Update last_synced_at
    account.last_synced_at = datetime.now(timezone.utc)

    await db.commit()

    logger.info(f"Sync complete for {account.email_address}: {new_count} new, {skipped_count} skipped")
    return {"fetched": len(raw_messages), "new": new_count, "skipped": skipped_count}


async def _find_or_create_thread(
    db: AsyncSession,
    user_id: uuid.UUID,
    subject: str,
    message_id: str,
    in_reply_to: Optional[str],
    references: Optional[str],
    date: Optional[datetime],
) -> Thread:
    """
    Find an existing thread to attach this message to, or create a new one.
    
    Threading logic:
    1. If in_reply_to matches an existing message's message_id_header → use that thread
    2. If references contain any known message_id_header → use that thread
    3. If subject matches (after stripping Re:/Fwd:) → use that thread
    4. Otherwise create a new thread
    """
    import re

    # Strategy 1: Match by in_reply_to
    if in_reply_to:
        result = await db.execute(
            select(Message.thread_id).where(
                Message.message_id_header == in_reply_to
            ).limit(1)
        )
        row = result.first()
        if row:
            thread_result = await db.execute(
                select(Thread).where(Thread.id == row[0])
            )
            thread = thread_result.scalar_one_or_none()
            if thread:
                return thread

    # Strategy 2: Match by references
    if references:
        ref_ids = references.split()
        for ref_id in reversed(ref_ids):  # Most recent reference first
            ref_id = ref_id.strip()
            if ref_id:
                result = await db.execute(
                    select(Message.thread_id).where(
                        Message.message_id_header == ref_id
                    ).limit(1)
                )
                row = result.first()
                if row:
                    thread_result = await db.execute(
                        select(Thread).where(Thread.id == row[0])
                    )
                    thread = thread_result.scalar_one_or_none()
                    if thread:
                        return thread

    # Strategy 3: Match by normalized subject
    normalized = re.sub(r"^(Re|Fwd|Fw)\s*:\s*", "", subject or "", flags=re.IGNORECASE).strip()
    if normalized:
        result = await db.execute(
            select(Thread).where(
                Thread.user_id == user_id,
                Thread.subject == normalized,
            ).order_by(Thread.last_message_at.desc().nullslast()).limit(1)
        )
        thread = result.scalar_one_or_none()
        if thread:
            return thread

    # Strategy 4: Create new thread
    thread = Thread(
        user_id=user_id,
        subject=normalized or subject or "(no subject)",
        message_count=0,
        last_message_at=date,
    )
    db.add(thread)
    await db.flush()  # Get the ID assigned
    return thread
