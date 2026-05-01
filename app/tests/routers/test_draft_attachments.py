"""
Tests for the Phase 9 D draft-restoration endpoints:
  GET    /api/messages/{message_id}/attachments
  POST   /api/messages/{message_id}/attachments
  DELETE /api/messages/{message_id}/attachments/{attachment_id}
  GET    /api/messages/{message_id}/attachments/{attachment_id}/download
         (existing — verifying it works for draft attachments)
"""
from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient, ASGITransport

from app.tests.conftest import requires_db


async def _client_with_auth_override(user):
    from app.main import app
    from app.middleware.auth import get_current_user

    async def _override():
        return user

    app.dependency_overrides[get_current_user] = _override
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test"), app


async def _make_draft(db, account, *, with_attachments=()):
    """Insert a draft Message with optional Attachment rows + on-disk files.

    `with_attachments` is a list of (filename, content_type, bytes).
    Returns (message, [attachment, ...]).
    """
    from app.models.message import Message
    from app.models.thread import Thread
    from app.models.attachment import Attachment
    from app.services import attachment_storage

    t = Thread(id=uuid.uuid4(), user_id=account.user_id, message_count=1)
    db.add(t)
    await db.flush()
    msg = Message(
        id=uuid.uuid4(),
        thread_id=t.id,
        account_id=account.id,
        from_address=account.email_address,
        to_addresses=[],
        cc_addresses=[],
        bcc_addresses=[],
        subject="draft",
        is_draft=True,
        is_read=True,
        has_attachments=bool(with_attachments),
    )
    db.add(msg)
    await db.flush()
    saved = []
    for filename, ctype, data in with_attachments:
        rec = await attachment_storage.save_bytes(data, content_type=ctype, filename=filename)
        att = Attachment(
            id=uuid.uuid4(),
            message_id=msg.id,
            filename=rec.filename,
            content_type=rec.content_type,
            size_bytes=rec.size_bytes,
            storage_path=rec.storage_path,
            is_inline=False,
        )
        db.add(att)
        saved.append(att)
    await db.commit()
    return msg, saved


# ---------------------------------------------------------------------------
# GET /attachments — list
# ---------------------------------------------------------------------------

@requires_db
class TestListAttachments:
    async def test_returns_metadata_only(self, db, user, account_a, tmp_path, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))

        msg, _ = await _make_draft(
            db, account_a,
            with_attachments=[
                ("a.txt", "text/plain", b"AAA"),
                ("b.bin", "application/octet-stream", b"BBBB"),
            ],
        )

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.get(f"/api/messages/{msg.id}/attachments")
            assert r.status_code == 200
            body = r.json()
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        assert len(body) == 2
        names = sorted(a["filename"] for a in body)
        assert names == ["a.txt", "b.bin"]
        # Metadata only — no data/bytes field in the response.
        for a in body:
            assert set(a.keys()) >= {"id", "filename", "content_type", "size_bytes"}
            assert "data" not in a

    async def test_empty_list_when_none(self, db, user, account_a):
        msg, _ = await _make_draft(db, account_a)

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.get(f"/api/messages/{msg.id}/attachments")
        finally:
            app.dependency_overrides.clear()
            await client.aclose()
        assert r.status_code == 200
        assert r.json() == []

    async def test_other_users_message_returns_404(self, db, user, account_a, other_user):
        msg, _ = await _make_draft(db, account_a)

        client, app = await _client_with_auth_override(other_user)
        try:
            r = await client.get(f"/api/messages/{msg.id}/attachments")
            assert r.status_code == 404
        finally:
            app.dependency_overrides.clear()
            await client.aclose()


# ---------------------------------------------------------------------------
# POST /attachments — upload to draft
# ---------------------------------------------------------------------------

@requires_db
class TestPostAttachmentsToDraft:
    async def test_upload_succeeds_on_draft(self, db, user, account_a, tmp_path, monkeypatch):
        from app.config import settings
        from sqlalchemy import select
        from app.models.attachment import Attachment

        monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))

        msg, _ = await _make_draft(db, account_a)

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.post(
                f"/api/messages/{msg.id}/attachments",
                files={"attachments": ("note.pdf", b"PDFBYTES", "application/pdf")},
            )
            assert r.status_code == 201
            body = r.json()
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        assert len(body) == 1
        assert body[0]["filename"] == "note.pdf"

        rows = (await db.execute(
            select(Attachment).where(Attachment.message_id == msg.id)
        )).scalars().all()
        assert len(rows) == 1
        assert (tmp_path / rows[0].storage_path).exists()

    async def test_post_to_sent_message_returns_400(self, db, user, account_a):
        # Build a sent message instead of a draft.
        from app.models.message import Message
        from app.models.thread import Thread
        t = Thread(id=uuid.uuid4(), user_id=account_a.user_id, message_count=1)
        db.add(t)
        await db.flush()
        sent = Message(
            id=uuid.uuid4(),
            thread_id=t.id,
            account_id=account_a.id,
            from_address=account_a.email_address,
            to_addresses=[], cc_addresses=[], bcc_addresses=[],
            subject="sent",
            is_draft=False, is_sent=True, is_read=True,
        )
        db.add(sent)
        await db.commit()

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.post(
                f"/api/messages/{sent.id}/attachments",
                files={"attachments": ("x.txt", b"x", "text/plain")},
            )
            assert r.status_code == 400
            assert "sent" in r.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

    async def test_size_cap_counts_existing_attachments(
        self, db, user, account_a, tmp_path, monkeypatch,
    ):
        from app.config import settings
        from sqlalchemy import select
        from app.models.attachment import Attachment

        monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))
        # Cap is 100 bytes. Seed a draft with 80 bytes already, then try
        # to upload 50 more — total 130 > 100, must reject.
        monkeypatch.setattr(settings, "ATTACHMENT_MAX_BYTES", 100)

        msg, existing = await _make_draft(
            db, account_a,
            with_attachments=[("seed.bin", "application/octet-stream", b"x" * 80)],
        )

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.post(
                f"/api/messages/{msg.id}/attachments",
                files={"attachments": ("addon.bin", b"y" * 50, "application/octet-stream")},
            )
            assert r.status_code == 413
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        # Existing seed attachment survived; no new row added.
        rows = (await db.execute(
            select(Attachment).where(Attachment.message_id == msg.id)
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].id == existing[0].id
        # No orphan file from the rejected upload.
        on_disk = sorted(p.name for p in tmp_path.iterdir())
        # Only the seed file should be present.
        assert on_disk == [existing[0].storage_path]

    async def test_filename_path_traversal_sanitized(
        self, db, user, account_a, tmp_path, monkeypatch,
    ):
        from app.config import settings
        monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))

        msg, _ = await _make_draft(db, account_a)

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.post(
                f"/api/messages/{msg.id}/attachments",
                files={"attachments": ("../../etc/passwd", b"x", "text/plain")},
            )
            assert r.status_code == 201
            assert r.json()[0]["filename"] == "passwd"
        finally:
            app.dependency_overrides.clear()
            await client.aclose()


# ---------------------------------------------------------------------------
# DELETE /attachments/{id}
# ---------------------------------------------------------------------------

@requires_db
class TestDeleteAttachment:
    async def test_delete_removes_row_and_file(
        self, db, user, account_a, tmp_path, monkeypatch,
    ):
        from app.config import settings
        from sqlalchemy import select
        from app.models.attachment import Attachment

        monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))

        msg, atts = await _make_draft(
            db, account_a,
            with_attachments=[("doc.pdf", "application/pdf", b"PDFDATA")],
        )
        on_disk = tmp_path / atts[0].storage_path
        assert on_disk.exists()

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.delete(
                f"/api/messages/{msg.id}/attachments/{atts[0].id}"
            )
            assert r.status_code == 204
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        # Row gone.
        remaining = (await db.execute(
            select(Attachment).where(Attachment.id == atts[0].id)
        )).scalar_one_or_none()
        assert remaining is None
        # File gone.
        assert not on_disk.exists()

    async def test_delete_other_users_attachment_returns_404(
        self, db, user, account_a, other_user, tmp_path, monkeypatch,
    ):
        from app.config import settings
        from sqlalchemy import select
        from app.models.attachment import Attachment

        monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))

        msg, atts = await _make_draft(
            db, account_a,
            with_attachments=[("x.txt", "text/plain", b"x")],
        )

        client, app = await _client_with_auth_override(other_user)
        try:
            r = await client.delete(
                f"/api/messages/{msg.id}/attachments/{atts[0].id}"
            )
            assert r.status_code == 404
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        # Row still exists.
        remaining = (await db.execute(
            select(Attachment).where(Attachment.id == atts[0].id)
        )).scalar_one_or_none()
        assert remaining is not None

    async def test_delete_with_missing_disk_file_succeeds(
        self, db, user, account_a, tmp_path, monkeypatch,
    ):
        """If the on-disk file is already gone (somehow), DELETE still
        succeeds and removes the row. Best-effort delete in the storage
        layer handles the missing file silently."""
        from app.config import settings
        from sqlalchemy import select
        from app.models.attachment import Attachment

        monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))

        msg, atts = await _make_draft(
            db, account_a,
            with_attachments=[("doc.pdf", "application/pdf", b"X")],
        )
        # Manually unlink the file to simulate the inconsistent state.
        (tmp_path / atts[0].storage_path).unlink()

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.delete(
                f"/api/messages/{msg.id}/attachments/{atts[0].id}"
            )
            assert r.status_code == 204
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        remaining = (await db.execute(
            select(Attachment).where(Attachment.id == atts[0].id)
        )).scalar_one_or_none()
        assert remaining is None

    async def test_delete_last_attachment_clears_has_attachments_flag(
        self, db, user, account_a, tmp_path, monkeypatch,
    ):
        from app.config import settings
        from sqlalchemy import select
        from app.models.message import Message

        monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))

        msg, atts = await _make_draft(
            db, account_a,
            with_attachments=[("only.txt", "text/plain", b"x")],
        )
        assert msg.has_attachments is True

        client, app = await _client_with_auth_override(user)
        try:
            await client.delete(f"/api/messages/{msg.id}/attachments/{atts[0].id}")
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        refreshed = (await db.execute(
            select(Message).where(Message.id == msg.id)
        )).scalar_one()
        assert refreshed.has_attachments is False


# ---------------------------------------------------------------------------
# GET /attachments/{id}/download — works for draft attachments + auth
# ---------------------------------------------------------------------------

@requires_db
class TestDownloadDraftAttachment:
    async def test_download_returns_disk_bytes(
        self, db, user, account_a, tmp_path, monkeypatch,
    ):
        from app.config import settings
        monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))

        msg, atts = await _make_draft(
            db, account_a,
            with_attachments=[("doc.pdf", "application/pdf", b"PDFBYTES12345")],
        )

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.get(
                f"/api/messages/{msg.id}/attachments/{atts[0].id}/download"
            )
            assert r.status_code == 200
            assert r.content == b"PDFBYTES12345"
            assert "doc.pdf" in r.headers.get("content-disposition", "")
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

    async def test_download_other_users_attachment_returns_404(
        self, db, user, account_a, other_user, tmp_path, monkeypatch,
    ):
        from app.config import settings
        monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))

        msg, atts = await _make_draft(
            db, account_a,
            with_attachments=[("x.txt", "text/plain", b"x")],
        )

        client, app = await _client_with_auth_override(other_user)
        try:
            r = await client.get(
                f"/api/messages/{msg.id}/attachments/{atts[0].id}/download"
            )
            assert r.status_code == 404
        finally:
            app.dependency_overrides.clear()
            await client.aclose()
