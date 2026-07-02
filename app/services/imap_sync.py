"""
IMAP Sync Service — fetch emails from a Stalwart (or any IMAP) mailbox
and write them into the threads + messages tables.

Uses stdlib imaplib wrapped in asyncio.to_thread for async compatibility.
"""

import asyncio
import email
import imaplib
import logging
import re
import uuid
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.thread import Thread
from app.models.message import Message
from app.models.folder import Folder
from app.services.classification import ClassificationBatch
from app.services.crypto import decrypt_credential

logger = logging.getLogger(__name__)


# ── Text sanitization ─────────────────────────────────

def _sanitize_text(text: str) -> Optional[str]:
    """Remove null bytes and other characters PostgreSQL can't store.
    Returns None if the result is empty or was not real text."""
    if not text:
        return None
    cleaned = text.replace("\x00", "")
    # If after cleaning the string is mostly non-printable, it was probably binary
    printable_ratio = sum(1 for c in cleaned[:200] if c.isprintable() or c in '\n\r\t') / max(len(cleaned[:200]), 1)
    if printable_ratio < 0.5:
        return None
    return cleaned


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
    """Parse 'Name <email>' into {name, address}.

    Address is lowercased + stripped at ingest (Phase 8). Display name
    preserves casing.
    """
    name, addr = parseaddr(raw)
    return {"name": decode_mime_header(name), "address": (addr or "").strip().lower()}


def parse_address_list(raw: str) -> list[dict]:
    """Parse a comma-separated address list."""
    if not raw:
        return []
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

            # Skip non-text parts entirely
            if not content_type.startswith("text/"):
                continue

            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
                decoded = _sanitize_text(decoded)
                if decoded is None:
                    continue
            except Exception:
                continue

            if content_type == "text/html" and not body_html:
                body_html = decoded
            elif content_type == "text/plain" and not body_text:
                body_text = decoded
    else:
        content_type = msg.get_content_type()
        if content_type.startswith("text/"):
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    decoded = payload.decode(charset, errors="replace")
                    decoded = _sanitize_text(decoded)
                    if decoded is not None:
                        if content_type == "text/html":
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


# ── IMAP folder helpers ────────────────────────────────

MAX_MESSAGES_PER_FOLDER = 200  # bound first-run backfill so we don't hammer the server

# Folder-name → category, matched case-insensitively on the leaf name.
# (Stalwart/Dovecot use "." or "/" as the hierarchy delimiter.)
_SENT_FOLDERS = {"sent", "sent items", "sent mail", "sent messages"}
_DRAFT_FOLDERS = {"drafts", "draft"}
_TRASH_FOLDERS = {"trash", "deleted", "deleted items", "deleted messages", "bin"}
_JUNK_FOLDERS = {"junk", "spam", "junk email", "junk e-mail"}
_ARCHIVE_FOLDERS = {"archive", "archived", "all mail"}
_SYSTEM_FOLDERS = (
    {"inbox"} | _SENT_FOLDERS | _DRAFT_FOLDERS | _TRASH_FOLDERS | _JUNK_FOLDERS | _ARCHIVE_FOLDERS
)

_LIST_RE = re.compile(r'^\((?P<flags>[^)]*)\)\s+(?:"[^"]*"|NIL|\S+)\s+(?P<name>.+)$')


def _folder_leaf(name: str) -> str:
    """Leaf name of a hierarchical mailbox path, delimiter-agnostic."""
    return name.rsplit("/", 1)[-1].rsplit(".", 1)[-1].strip()


def _categorize_folder(name: str) -> dict:
    """Map an IMAP folder name to the message flags it implies."""
    leaf = _folder_leaf(name).lower()
    return {
        "is_sent": leaf in _SENT_FOLDERS,
        "is_draft": leaf in _DRAFT_FOLDERS,
        "is_trashed": leaf in _TRASH_FOLDERS,
        "is_spam": leaf in _JUNK_FOLDERS,
        "is_archived": leaf in _ARCHIVE_FOLDERS,
        "is_system": leaf in _SYSTEM_FOLDERS,
    }


def _imap_quote(name: str) -> str:
    """Quote a mailbox name for SELECT (handles spaces)."""
    return '"' + name.replace('"', '\\"') + '"'


def _parse_list_line(line) -> Optional[str]:
    """Extract a selectable mailbox name from one LIST response line."""
    if isinstance(line, tuple):
        line = line[0]
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    if not isinstance(line, str):
        return None
    m = _LIST_RE.match(line.strip())
    if not m:
        return None
    if "\\Noselect" in m.group("flags") or "\\NonExistent" in m.group("flags"):
        return None
    name = m.group("name").strip()
    if len(name) >= 2 and name[0] == '"' and name[-1] == '"':
        name = name[1:-1]
    return name or None


def _parse_fetch_meta(meta) -> tuple[Optional[str], set]:
    """Pull the UID and FLAGS out of a FETCH response metadata line."""
    if isinstance(meta, bytes):
        meta = meta.decode("utf-8", errors="replace")
    uid = None
    m = re.search(r"\bUID\s+(\d+)", meta)
    if m:
        uid = m.group(1)
    flags = set()
    fm = re.search(r"FLAGS\s+\(([^)]*)\)", meta)
    if fm:
        flags = set(fm.group(1).split())
    return uid, flags


# ── IMAP fetching (synchronous, runs in thread) ───────

def _imap_fetch_all(
    host: str,
    port: int,
    username: str,
    password: str,
    max_per_folder: int = MAX_MESSAGES_PER_FOLDER,
) -> list[dict]:
    """Connect to IMAP and fetch messages from every selectable folder.

    Returns a list of {folder, uid, flags, raw} dicts (the newest
    ``max_per_folder`` per folder). Runs synchronously in a worker thread.
    """
    logger.info(f"Connecting to IMAP {host}:{port} as {username}")

    mail = imaplib.IMAP4_SSL(host, port)
    mail.login(username, password)

    records: list[dict] = []
    try:
        status, list_data = mail.list()
        folders: list[str] = []
        if status == "OK" and list_data:
            for line in list_data:
                parsed = _parse_list_line(line)
                if parsed:
                    folders.append(parsed)
        if not folders:
            folders = ["INBOX"]

        for folder in folders:
            try:
                status, _ = mail.select(_imap_quote(folder), readonly=True)
                if status != "OK":
                    logger.warning("Could not select folder %s", folder)
                    continue

                status, data = mail.search(None, "ALL")
                if status != "OK" or not data or not data[0]:
                    continue

                nums = data[0].split()
                if max_per_folder and len(nums) > max_per_folder:
                    nums = nums[-max_per_folder:]
                logger.info("Fetching %d message(s) from %s", len(nums), folder)

                for num in nums:
                    status, msg_data = mail.fetch(num, "(UID FLAGS RFC822)")
                    if status != "OK" or not msg_data or msg_data[0] is None:
                        continue
                    if isinstance(msg_data[0], tuple):
                        uid, flags = _parse_fetch_meta(msg_data[0][0])
                        records.append({
                            "folder": folder,
                            "uid": uid,
                            "flags": flags,
                            "raw": msg_data[0][1],
                        })
            except Exception as e:
                logger.warning("Skipping folder %s: %s", folder, e)
                continue
    finally:
        try:
            mail.logout()
        except Exception:
            pass

    return records


def _imap_move(host, port, username, password, dest_folder: str, by_source: dict) -> int:
    """Move messages to dest_folder on the server. Runs synchronously.

    by_source maps a source mailbox name → list of UID strings. Uses UID MOVE
    (RFC 6851) with a COPY+delete+EXPUNGE fallback for servers without it.
    """
    mail = imaplib.IMAP4_SSL(host, port)
    mail.login(username, password)
    moved = 0
    dest = _imap_quote(dest_folder)
    try:
        for source, uids in by_source.items():
            uids = [u for u in uids if u]
            if not uids:
                continue
            try:
                status, _ = mail.select(_imap_quote(source))  # read-write
                if status != "OK":
                    logger.warning("Move: could not select %s", source)
                    continue
                uid_set = ",".join(uids)
                try:
                    typ, _ = mail.uid("MOVE", uid_set, dest)
                    ok = typ == "OK"
                except Exception:
                    ok = False
                if not ok:
                    mail.uid("COPY", uid_set, dest)
                    mail.uid("STORE", uid_set, "+FLAGS", r"(\Deleted)")
                    mail.expunge()
                moved += len(uids)
            except Exception as e:
                logger.warning("IMAP move from %s to %s failed: %s", source, dest_folder, e)
                continue
    finally:
        try:
            mail.logout()
        except Exception:
            pass
    return moved


async def move_messages_to_folder(account: Account, messages: list, dest_folder: str) -> int:
    """Move the given messages to dest_folder on the IMAP server (best effort).

    Derives the source mailbox + UID from each message's remote_id
    (``{folder}:{uid}``). Legacy ``stalwart:{uid}`` ids are treated as INBOX.
    Messages with no server-side id (locally composed, never synced) are skipped.
    """
    if not account.imap_host or not account.username or not account.password:
        return 0

    by_source: dict[str, list[str]] = {}
    for m in messages:
        rid = getattr(m, "remote_id", None)
        if not rid or ":" not in rid:
            continue
        source, uid = rid.rsplit(":", 1)
        if source == "stalwart":
            source = "INBOX"  # pre-folder-aware remote_id scheme
        if not uid.isdigit():
            continue
        by_source.setdefault(source, []).append(uid)

    if not by_source:
        return 0

    password = decrypt_credential(account.password)
    return await asyncio.to_thread(
        _imap_move,
        account.imap_host,
        account.imap_port or 993,
        account.username,
        password,
        dest_folder,
        by_source,
    )


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

    # Passwords are stored Fernet-encrypted (see app/services/crypto.py).
    # Decrypt before handing the credential to imaplib, or every login fails.
    password = decrypt_credential(account.password)

    try:
        records = await asyncio.to_thread(
            _imap_fetch_all,
            account.imap_host,
            account.imap_port or 993,
            account.username,
            password,
        )
    except Exception as e:
        logger.error(f"IMAP fetch failed for {account.email_address}: {e}")
        return {"error": f"IMAP connection failed: {str(e)}"}

    if not records:
        return {"fetched": 0, "new": 0, "skipped": 0}

    # Get existing message_id_headers to avoid duplicates
    existing_result = await db.execute(
        select(Message.message_id_header).where(
            Message.account_id == account.id,
            Message.message_id_header.isnot(None),
        )
    )
    existing_msg_ids = set(row[0] for row in existing_result.all())

    existing_remote_result = await db.execute(
        select(Message.remote_id).where(
            Message.account_id == account.id,
            Message.remote_id.isnot(None),
        )
    )
    existing_remote_ids = set(row[0] for row in existing_remote_result.all())

    # Cache of folder name → Folder.id, seeded from existing rows; missing
    # folders are created lazily as we encounter their messages.
    existing_folders = await db.execute(
        select(Folder).where(Folder.account_id == account.id)
    )
    folder_ids: dict[str, uuid.UUID] = {
        f.remote_id: f.id for f in existing_folders.scalars().all() if f.remote_id
    }

    async def _folder_id_for(name: str) -> uuid.UUID:
        if name in folder_ids:
            return folder_ids[name]
        cat = _categorize_folder(name)
        folder = Folder(
            account_id=account.id,
            name=_folder_leaf(name) or name,
            remote_id=name,
            folder_type="system" if cat["is_system"] else "custom",
        )
        db.add(folder)
        await db.flush()
        folder_ids[name] = folder.id
        return folder.id

    new_count = 0
    skipped_count = 0

    # One classifier batch per sync run.
    classifier = ClassificationBatch(db, account.id, user_id)

    for rec in records:
        folder_name = rec["folder"]
        uid = rec["uid"]
        imap_flags = rec["flags"]
        msg = email.message_from_bytes(rec["raw"])

        message_id = msg.get("Message-ID", "").strip()
        remote_id = f"{folder_name}:{uid}" if uid else None

        # Skip duplicates. Message-ID is the primary key across folders so a
        # message already synced from INBOX isn't re-imported under its new
        # folder-scoped remote_id.
        if message_id and message_id in existing_msg_ids:
            skipped_count += 1
            continue
        if remote_id and remote_id in existing_remote_ids:
            skipped_count += 1
            continue

        # Folder → category flags, plus IMAP \Seen / \Flagged / \Draft state.
        cat = _categorize_folder(folder_name)
        folder_id = await _folder_id_for(folder_name)
        is_sent = cat["is_sent"]
        is_draft = cat["is_draft"] or ("\\Draft" in imap_flags)
        is_read = ("\\Seen" in imap_flags) or is_sent or is_draft
        is_starred = "\\Flagged" in imap_flags

        # Parse headers
        subject = decode_mime_header(msg.get("Subject", ""))
        from_parsed = parse_address(msg.get("From", ""))
        to_list = parse_address_list(msg.get("To", ""))
        cc_list = parse_address_list(msg.get("Cc", ""))
        in_reply_to = msg.get("In-Reply-To", "").strip() or None
        references_header = msg.get("References", "").strip() or None
        date = parse_date(msg)

        # Get body (with sanitization)
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

        # Classify People / Bulk before INSERT. Sent/draft mail is authored by
        # the user, not received, so skip the classifier for those.
        if is_sent or is_draft:
            category, category_source = "people", "default"
        else:
            classifier_headers = {k: v for k, v in msg.items()}
            category, category_source = await classifier.classify(
                from_address=from_parsed["address"],
                headers=classifier_headers,
                content_type=msg.get("Content-Type"),
                remote_id=remote_id,
            )

        # Create message
        new_message = Message(
            thread_id=thread.id,
            account_id=account.id,
            folder_id=folder_id,
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
            is_read=is_read,
            is_starred=is_starred,
            is_draft=is_draft,
            is_sent=is_sent,
            is_trashed=cat["is_trashed"],
            is_archived=cat["is_archived"],
            is_spam=cat["is_spam"],
            has_attachments=attachment_count > 0,
            received_at=date,
            category=category,
            category_source=category_source,
        )
        db.add(new_message)

        # Update thread atomically
        # synchronize_session=False: the SQL expression in .values() isn't
        # Python-evaluable, so default "auto" mode falls back to "fetch" and
        # expires the in-session `thread`. The next attribute read would
        # then trigger an implicit async refresh and raise greenlet_spawn.
        await db.execute(
            update(Thread)
            .where(Thread.id == thread.id)
            .values(message_count=Thread.message_count + 1)
            .execution_options(synchronize_session=False)
        )
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

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.warning(f"Duplicate message(s) detected during batch commit for {account.email_address}, rolling back batch")
        return {"fetched": len(records), "new": 0, "skipped": len(records)}

    logger.info(f"Sync complete for {account.email_address}: {new_count} new, {skipped_count} skipped")
    return {"fetched": len(records), "new": new_count, "skipped": skipped_count}


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
        for ref_id in reversed(ref_ids):
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

    # Strategy 3: Create new thread
    normalized = re.sub(r"^(Re|Fwd|Fw)\s*:\s*", "", subject or "", flags=re.IGNORECASE).strip()
    thread = Thread(
        user_id=user_id,
        subject=normalized or subject or "(no subject)",
        message_count=0,
        last_message_at=date,
    )
    db.add(thread)
    await db.flush()
    return thread
