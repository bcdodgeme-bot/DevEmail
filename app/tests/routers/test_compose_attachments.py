"""
Tests for the Phase 9 compose-with-attachments endpoint.

Most cover the multipart parsing + size-cap enforcement + draft-vs-send
flows and need a real DB (auth, Message + Attachment rows). Pure-Python
tests cover the JSON-vs-multipart dispatch on the parser.
"""
from __future__ import annotations

import io
import json
import uuid
from unittest.mock import AsyncMock, patch

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


def _payload(account_id, *, is_draft=True, subject="Hi", to=("bob@example.com",)):
    return {
        "account_id": str(account_id),
        "to_addresses": [{"address": a} for a in to],
        "subject": subject,
        "body_text": "body",
        "is_draft": is_draft,
    }


# ---------------------------------------------------------------------------
# Pure-Python: GET /messages/config/attachments
# ---------------------------------------------------------------------------

@requires_db
class TestAttachmentConfig:
    async def test_returns_max_bytes_from_settings(self, db, user, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "ATTACHMENT_MAX_BYTES", 12345)

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.get("/api/messages/config/attachments")
            assert r.status_code == 200
            assert r.json() == {"max_bytes": 12345}
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

    async def test_config_route_not_shadowed_by_message_id_attachments(
        self, db, user, monkeypatch,
    ):
        """
        Regression: GET /api/messages/config/attachments was being matched as
        GET /api/messages/{message_id}/attachments with message_id='config',
        which triggered an asyncpg UUID-parse failure (DataError 'invalid
        UUID config'). Static routes must be declared before parameterized
        routes that share their first segment.

        This test fails if /config/attachments is registered AFTER any
        /{message_id}/... route.
        """
        from app.config import settings
        monkeypatch.setattr(settings, "ATTACHMENT_MAX_BYTES", 999)

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.get("/api/messages/config/attachments")
            # Specifically NOT a 500: that's what shadowing produces.
            assert r.status_code == 200, (
                f"Expected 200, got {r.status_code}. "
                f"If this is 500, /{{message_id}}/attachments is shadowing "
                f"/config/attachments — check route registration order."
            )
            assert r.json() == {"max_bytes": 999}
        finally:
            app.dependency_overrides.clear()
            await client.aclose()


# ---------------------------------------------------------------------------
# DB-bound: multipart compose
# ---------------------------------------------------------------------------

@requires_db
class TestComposeMultipartDraft:
    async def test_single_attachment_saved_to_disk_and_db(
        self, db, user, account_a, tmp_path, monkeypatch,
    ):
        from app.config import settings
        from sqlalchemy import select
        from app.models.attachment import Attachment
        from app.models.message import Message

        monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.post(
                "/api/messages/compose",
                data={"payload": json.dumps(_payload(account_a.id, is_draft=True))},
                files={"attachments": ("note.txt", b"hello world", "text/plain")},
            )
            assert r.status_code == 201
            body = r.json()
            assert body["status"] == "draft"
            message_id = uuid.UUID(body["message_id"])
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        # DB row created.
        atts = (await db.execute(
            select(Attachment).where(Attachment.message_id == message_id)
        )).scalars().all()
        assert len(atts) == 1
        att = atts[0]
        assert att.filename == "note.txt"
        assert att.content_type == "text/plain"
        assert att.size_bytes == len(b"hello world")
        assert att.storage_path is not None
        # Disk file exists in the configured dir.
        on_disk = tmp_path / att.storage_path
        assert on_disk.exists()
        assert on_disk.read_bytes() == b"hello world"

        # Message marked has_attachments.
        msg = (await db.execute(
            select(Message).where(Message.id == message_id)
        )).scalar_one()
        assert msg.has_attachments is True
        assert msg.is_draft is True

    async def test_multiple_attachments(self, db, user, account_a, tmp_path, monkeypatch):
        from app.config import settings
        from sqlalchemy import select
        from app.models.attachment import Attachment

        monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.post(
                "/api/messages/compose",
                data={"payload": json.dumps(_payload(account_a.id, is_draft=True))},
                files=[
                    ("attachments", ("a.txt", b"AAA", "text/plain")),
                    ("attachments", ("b.bin", b"BBBB", "application/octet-stream")),
                ],
            )
            assert r.status_code == 201
            message_id = uuid.UUID(r.json()["message_id"])
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        atts = (await db.execute(
            select(Attachment).where(Attachment.message_id == message_id)
        )).scalars().all()
        names = sorted(a.filename for a in atts)
        assert names == ["a.txt", "b.bin"]

    async def test_size_cap_enforced(self, db, user, account_a, tmp_path, monkeypatch):
        from app.config import settings
        from sqlalchemy import select
        from app.models.attachment import Attachment
        from app.models.message import Message

        monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))
        monkeypatch.setattr(settings, "ATTACHMENT_MAX_BYTES", 100)

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.post(
                "/api/messages/compose",
                data={"payload": json.dumps(_payload(account_a.id, is_draft=True))},
                files={"attachments": ("big.bin", b"x" * 1024, "application/octet-stream")},
            )
            assert r.status_code == 413
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        # No DB rows should have been created — the rollback must have
        # caught both the Message and the Attachment.
        rows = (await db.execute(select(Message).where(Message.account_id == account_a.id))).scalars().all()
        assert len(rows) == 0
        atts = (await db.execute(select(Attachment))).scalars().all()
        assert len(atts) == 0
        # And no orphan files on disk.
        leftover = list(tmp_path.iterdir()) if tmp_path.exists() else []
        assert leftover == [], f"orphan files left after cap-rejected upload: {leftover}"

    async def test_filename_with_path_traversal_sanitized(
        self, db, user, account_a, tmp_path, monkeypatch,
    ):
        from app.config import settings
        from sqlalchemy import select
        from app.models.attachment import Attachment

        monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.post(
                "/api/messages/compose",
                data={"payload": json.dumps(_payload(account_a.id, is_draft=True))},
                files={"attachments": ("../../etc/passwd", b"x", "text/plain")},
            )
            assert r.status_code == 201
            message_id = uuid.UUID(r.json()["message_id"])
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        atts = (await db.execute(
            select(Attachment).where(Attachment.message_id == message_id)
        )).scalars().all()
        assert len(atts) == 1
        # Sanitization stripped the path components.
        assert atts[0].filename == "passwd"


# ---------------------------------------------------------------------------
# DB-bound: send path with mocked transport
# ---------------------------------------------------------------------------

@requires_db
class TestComposeMultipartSend:
    async def test_send_success_flips_draft_to_sent(
        self, db, user, account_a, tmp_path, monkeypatch,
    ):
        from app.config import settings
        from sqlalchemy import select
        from app.models.attachment import Attachment
        from app.models.message import Message
        import app.services.email_send as email_send

        monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))

        # Stub the provider transport — we don't actually want to hit Gmail.
        async def _fake_send_gmail(self, mime_msg):
            return "fake-gmail-id-123"
        monkeypatch.setattr(email_send.EmailSendService, "_send_gmail", _fake_send_gmail)

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.post(
                "/api/messages/compose",
                data={"payload": json.dumps(_payload(account_a.id, is_draft=False))},
                files={"attachments": ("doc.pdf", b"PDFBYTES", "application/pdf")},
            )
            assert r.status_code == 201
            assert r.json()["status"] == "sent"
            message_id = uuid.UUID(r.json()["message_id"])
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        msg = (await db.execute(select(Message).where(Message.id == message_id))).scalar_one()
        assert msg.is_draft is False
        assert msg.is_sent is True
        assert msg.remote_id == "fake-gmail-id-123"
        assert msg.has_attachments is True

        # Attachment row stays linked to the (now-sent) Message.
        atts = (await db.execute(
            select(Attachment).where(Attachment.message_id == message_id)
        )).scalars().all()
        assert len(atts) == 1

    async def test_send_failure_keeps_draft(
        self, db, user, account_a, tmp_path, monkeypatch,
    ):
        from app.config import settings
        from sqlalchemy import select
        from app.models.attachment import Attachment
        from app.models.message import Message
        import app.services.email_send as email_send

        monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))

        async def _broken_send_gmail(self, mime_msg):
            raise RuntimeError("simulated SMTP failure")
        monkeypatch.setattr(email_send.EmailSendService, "_send_gmail", _broken_send_gmail)

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.post(
                "/api/messages/compose",
                data={"payload": json.dumps(_payload(account_a.id, is_draft=False))},
                files={"attachments": ("doc.pdf", b"X", "application/pdf")},
            )
            assert r.status_code == 502
            assert "Drafts folder" in r.json()["detail"]
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        # Draft survives. Attachment row + on-disk file survive too.
        drafts = (await db.execute(
            select(Message).where(
                Message.account_id == account_a.id,
                Message.is_draft.is_(True),
            )
        )).scalars().all()
        assert len(drafts) == 1
        atts = (await db.execute(
            select(Attachment).where(Attachment.message_id == drafts[0].id)
        )).scalars().all()
        assert len(atts) == 1
        assert (tmp_path / atts[0].storage_path).exists()


# ---------------------------------------------------------------------------
# DB-bound: JSON-only path still works (no attachments, backward-compat)
# ---------------------------------------------------------------------------

@requires_db
class TestComposeJSONBackwardCompat:
    async def test_json_no_attachments_saves_draft(self, db, user, account_a):
        from sqlalchemy import select
        from app.models.attachment import Attachment
        from app.models.message import Message

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.post(
                "/api/messages/compose",
                json=_payload(account_a.id, is_draft=True),
            )
            assert r.status_code == 201
            assert r.json()["status"] == "draft"
            message_id = uuid.UUID(r.json()["message_id"])
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        msg = (await db.execute(select(Message).where(Message.id == message_id))).scalar_one()
        assert msg.is_draft is True
        assert msg.has_attachments is False

        atts = (await db.execute(
            select(Attachment).where(Attachment.message_id == message_id)
        )).scalars().all()
        assert atts == []
