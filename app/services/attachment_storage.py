"""
Attachment storage layer (Phase 9).

Persists outbound (compose-uploaded) attachment bytes to disk under
ATTACHMENT_STORAGE_DIR. The DB row is the source of truth for everything
else (filename, content-type, size, message linkage); this module owns
only the bytes-on-disk concern.

Design notes
------------
- `storage_path` in the DB is RELATIVE to ATTACHMENT_STORAGE_DIR (just a
  UUID string). Absolute paths are reconstructed inside this module so
  the directory can be relocated without rewriting rows.
- On-disk files use a UUID for their name with no extension. The original
  user-facing filename lives in `attachments.filename` and is what gets
  written to the MIME `Content-Disposition: attachment; filename=...`
  header. Decoupling avoids both extension-based MIME spoofing and
  filename-collision bugs.
- I/O uses `aiofiles` to keep the event loop responsive — a 25 MiB write
  on commodity SSD blocks ~125 ms, which is unacceptable on the same
  loop serving HTTP.
- `delete()` is best-effort: missing files are not an error. The DB row
  is the authority; if the file is already gone, the desired post-state
  is satisfied.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiofiles
import aiofiles.os

from app.config import settings

logger = logging.getLogger(__name__)


# Reasonable safety net: the DB column is varchar(500), the MIME header
# accepts effectively unbounded but mail clients truncate around 200.
_FILENAME_MAX_LEN = 255
_FILENAME_BAD_CHARS = re.compile(r"[\x00-\x1f/\\]")  # control chars + path seps


@dataclass(frozen=True)
class AttachmentRecord:
    """Result of a successful save_bytes(). Caller writes the DB row."""
    storage_path: str   # relative to ATTACHMENT_STORAGE_DIR
    filename: str       # sanitized; safe to store and to put in MIME header
    content_type: str
    size_bytes: int


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _root() -> Path:
    """Resolved storage root. Recomputed each call so test overrides stick."""
    return Path(settings.ATTACHMENT_STORAGE_DIR).resolve()


def _absolute(storage_path: str) -> Path:
    """
    Resolve a relative `storage_path` against the storage root, refusing
    any path that would escape the root (defense in depth — we wrote
    these paths ourselves, but a stray '..' from a future bug shouldn't
    let an attacker scribble outside).
    """
    root = _root()
    candidate = (root / storage_path).resolve()
    # Path.is_relative_to landed in 3.9; guard via try/except for older runs.
    try:
        candidate.relative_to(root)
    except ValueError:
        raise ValueError(
            f"storage_path {storage_path!r} resolves outside ATTACHMENT_STORAGE_DIR"
        )
    return candidate


def _sanitize_filename(filename: Optional[str]) -> str:
    """
    Strip any path components, control characters, and null bytes from a
    user-supplied filename. Returns a non-empty string suitable for both
    the DB column and the MIME Content-Disposition filename parameter.

    Handles both '/' and '\\' separators explicitly — os.path.basename is
    platform-specific (no-op for '\\' on POSIX), and we want the same
    result on every host.
    """
    if not filename:
        return "attachment"
    # Drop directory parts regardless of which separator the client sent.
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    # Strip control chars and any remaining path separators.
    cleaned = _FILENAME_BAD_CHARS.sub("", base).strip().strip(".")
    if not cleaned:
        return "attachment"
    if len(cleaned) > _FILENAME_MAX_LEN:
        # Try to preserve the extension when truncating.
        stem, dot, ext = cleaned.rpartition(".")
        if dot and len(ext) <= 16:
            keep = _FILENAME_MAX_LEN - len(ext) - 1
            cleaned = (stem[:keep] if keep > 0 else stem[:1]) + "." + ext
        else:
            cleaned = cleaned[:_FILENAME_MAX_LEN]
    return cleaned


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def save_bytes(
    data: bytes,
    *,
    content_type: str,
    filename: Optional[str],
) -> AttachmentRecord:
    """
    Persist `data` to ATTACHMENT_STORAGE_DIR/<uuid>. Creates the directory
    on first write.

    Returns the AttachmentRecord the caller should use to insert the
    `attachments` DB row. Storage_path is relative.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("data must be bytes")

    safe_name = _sanitize_filename(filename)

    # Ensure the storage root exists. mkdir -p semantics, idempotent.
    root = _root()
    await aiofiles.os.makedirs(root, exist_ok=True)

    # The on-disk filename is a UUID with no extension — the DB row owns
    # the human filename. This makes traversal/mime-spoofing impossible.
    relative = uuid.uuid4().hex
    absolute = root / relative

    async with aiofiles.open(absolute, "wb") as f:
        await f.write(data)

    return AttachmentRecord(
        storage_path=relative,
        filename=safe_name,
        content_type=content_type or "application/octet-stream",
        size_bytes=len(data),
    )


async def read_bytes(storage_path: str) -> bytes:
    """Load the on-disk bytes for an attachment whose storage_path is the
    relative form stored in the DB."""
    absolute = _absolute(storage_path)
    async with aiofiles.open(absolute, "rb") as f:
        return await f.read()


async def delete(storage_path: Optional[str]) -> None:
    """
    Best-effort delete. Missing files are not an error — the DB row is the
    authority, and if the file is already gone the post-state is satisfied.
    """
    if not storage_path:
        return
    try:
        absolute = _absolute(storage_path)
    except ValueError:
        # Path traversal attempt or bad data — log and bail without
        # touching the filesystem.
        logger.warning("Refusing to delete suspicious storage_path: %r", storage_path)
        return
    try:
        await aiofiles.os.remove(absolute)
    except FileNotFoundError:
        pass
    except OSError as e:
        # Don't let a stray FS error fail the calling transaction. Caller
        # has already (or will) commit the DB delete; an orphaned file is
        # recoverable, lost data isn't.
        logger.warning("Failed to delete attachment file %s: %s", storage_path, e)
