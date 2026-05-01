"""
Tests for the People/Bulk API endpoints.

Most checks need a real DB (auth, message rows, override propagation), so
they're behind @requires_db. The query-param validation test for
?category=invalid is pure FastAPI / Pydantic and runs without a DB.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient, ASGITransport

from app.tests.conftest import requires_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _client_with_auth_override(user):
    """Build an AsyncClient that bypasses get_current_user, returning `user`."""
    from app.main import app
    from app.middleware.auth import get_current_user

    async def _override():
        return user

    app.dependency_overrides[get_current_user] = _override
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test"), app


async def _add_message(
    db, account, *, from_address, category="people", category_source="default",
    is_sent=False, is_archived=False, is_trashed=False, is_read=True,
):
    from app.models.message import Message
    from app.models.thread import Thread

    t = Thread(id=uuid.uuid4(), user_id=account.user_id, message_count=1)
    db.add(t)
    await db.flush()

    m = Message(
        id=uuid.uuid4(),
        thread_id=t.id,
        account_id=account.id,
        from_address=from_address,
        to_addresses=[],
        cc_addresses=[],
        bcc_addresses=[],
        subject="t",
        is_read=is_read,
        is_sent=is_sent,
        is_archived=is_archived,
        is_trashed=is_trashed,
        category=category,
        category_source=category_source,
    )
    db.add(m)
    await db.flush()
    return m


# ---------------------------------------------------------------------------
# Pure-Python: query param validation
# ---------------------------------------------------------------------------

class TestQueryValidation:
    def test_invalid_category_param_returns_422(self):
        # FastAPI validates the regex param before any handler runs.
        from fastapi.testclient import TestClient
        from app.main import app
        from app.middleware.auth import get_current_user

        # Bypass auth so we reach the validator.
        async def _no_auth():
            class _U:
                id = uuid.uuid4()
            return _U()

        app.dependency_overrides[get_current_user] = _no_auth
        try:
            with TestClient(app) as c:
                r = c.get("/api/messages/inbox?category=invalid")
                assert r.status_code == 422
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# DB-bound: filter, counts, manual move
# ---------------------------------------------------------------------------

@requires_db
class TestInboxFilter:
    async def test_category_bulk_filters_correctly(self, db, account_a, user):
        await _add_message(db, account_a, from_address="a@x.com", category="people")
        await _add_message(db, account_a, from_address="b@x.com", category="bulk")
        await db.commit()

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.get("/api/messages/inbox?category=bulk")
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 1
        finally:
            app.dependency_overrides.clear()
            await client.aclose()


@requires_db
class TestCategoryCounts:
    async def test_returns_correct_counts(self, db, account_a, user):
        # 3 people (2 unread), 2 bulk (1 unread). 1 archived people doesn't count.
        await _add_message(db, account_a, from_address="p1@x.com", category="people", is_read=False)
        await _add_message(db, account_a, from_address="p2@x.com", category="people", is_read=False)
        await _add_message(db, account_a, from_address="p3@x.com", category="people", is_read=True)
        await _add_message(db, account_a, from_address="b1@x.com", category="bulk",   is_read=False)
        await _add_message(db, account_a, from_address="b2@x.com", category="bulk",   is_read=True)
        await _add_message(db, account_a, from_address="archived@x.com",
                           category="people", is_read=False, is_archived=True)
        await db.commit()

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.get("/api/messages/category-counts")
            assert r.status_code == 200
            body = r.json()
            assert body["all"]["total"] == 5
            assert body["all"]["unread"] == 3
            assert body["people"]["total"] == 3
            assert body["people"]["unread"] == 2
            assert body["bulk"]["total"] == 2
            assert body["bulk"]["unread"] == 1
        finally:
            app.dependency_overrides.clear()
            await client.aclose()


@requires_db
class TestManualMove:
    async def test_creates_classification_row_first_time(self, db, account_a, user):
        m = await _add_message(db, account_a, from_address="x@y.com", category="people")
        await db.commit()

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.patch(
                f"/api/messages/{m.id}/category",
                json={"category": "bulk", "apply_to_domain": False, "apply_to_existing": False},
            )
            assert r.status_code == 200
            assert r.json()["category"] == "bulk"
            assert r.json()["category_source"] == "override"
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        # Verify the rule was inserted.
        from sqlalchemy import select
        from app.models.sender_classification import SenderClassification
        rows = (await db.execute(
            select(SenderClassification).where(
                SenderClassification.account_id == account_a.id,
                SenderClassification.sender_address == "x@y.com",
            )
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].category == "bulk"
        assert rows[0].learned_from == "manual_move"

    async def test_both_unchecked_still_writes_classification_row(self, db, account_a, user):
        """
        Phase 8 D verification (lock-in): a manual move with both checkboxes
        UNCHECKED must still upsert a sender_classifications row. Otherwise
        the next message from this sender would reclassify back to default
        and the user's intent would be forgotten.

        Behaviour: address-level rule (is_domain_rule=False), category set
        to the move target, learned_from='manual_move', and only the target
        message is touched (applied_to_existing_count == 0).
        """
        from sqlalchemy import select
        from app.models.message import Message
        from app.models.sender_classification import SenderClassification

        target = await _add_message(db, account_a, from_address="single@x.com", category="people")
        # A pre-existing message from the same sender that should NOT move.
        sibling = await _add_message(db, account_a, from_address="single@x.com", category="people")
        await db.commit()

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.patch(
                f"/api/messages/{target.id}/category",
                json={"category": "bulk", "apply_to_domain": False, "apply_to_existing": False},
            )
            assert r.status_code == 200
            assert r.json()["applied_to_existing_count"] == 0
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        # 1. Rule was created, address-level, learned_from='manual_move'.
        rules = (await db.execute(
            select(SenderClassification).where(
                SenderClassification.account_id == account_a.id,
                SenderClassification.sender_address == "single@x.com",
            )
        )).scalars().all()
        assert len(rules) == 1
        assert rules[0].is_domain_rule is False
        assert rules[0].category == "bulk"
        assert rules[0].learned_from == "manual_move"

        # 2. Target moved.
        target_row = (await db.execute(select(Message).where(Message.id == target.id))).scalar_one()
        assert target_row.category == "bulk"
        assert target_row.category_source == "override"

        # 3. Sibling NOT moved (apply_to_existing was False).
        sibling_row = (await db.execute(select(Message).where(Message.id == sibling.id))).scalar_one()
        assert sibling_row.category == "people"
        assert sibling_row.category_source == "default"

    async def test_second_call_updates_existing_rule(self, db, account_a, user):
        m = await _add_message(db, account_a, from_address="x@y.com", category="people")
        await db.commit()

        client, app = await _client_with_auth_override(user)
        try:
            await client.patch(
                f"/api/messages/{m.id}/category",
                json={"category": "bulk", "apply_to_domain": False, "apply_to_existing": False},
            )
            await client.patch(
                f"/api/messages/{m.id}/category",
                json={"category": "people", "apply_to_domain": False, "apply_to_existing": False},
            )
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        from sqlalchemy import select
        from app.models.sender_classification import SenderClassification
        rows = (await db.execute(
            select(SenderClassification).where(
                SenderClassification.account_id == account_a.id,
                SenderClassification.sender_address == "x@y.com",
                SenderClassification.is_domain_rule.is_(False),
            )
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].category == "people"

    async def test_apply_to_existing_address_level(self, db, account_a, user):
        # 3 messages from same sender, 1 from another sender.
        m1 = await _add_message(db, account_a, from_address="news@x.com", category="people")
        m2 = await _add_message(db, account_a, from_address="news@x.com", category="people")
        m3 = await _add_message(db, account_a, from_address="news@x.com", category="people")
        m_other = await _add_message(db, account_a, from_address="friend@x.com", category="people")
        await db.commit()

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.patch(
                f"/api/messages/{m1.id}/category",
                json={"category": "bulk", "apply_to_domain": False, "apply_to_existing": True},
            )
            assert r.status_code == 200
            # m1 is the target; m2 and m3 are the "existing" ones updated.
            assert r.json()["applied_to_existing_count"] == 2
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        from sqlalchemy import select
        from app.models.message import Message
        for mid in (m1.id, m2.id, m3.id):
            row = (await db.execute(select(Message).where(Message.id == mid))).scalar_one()
            assert row.category == "bulk"
            assert row.category_source == "override"
        # The other sender must NOT be touched.
        other = (await db.execute(select(Message).where(Message.id == m_other.id))).scalar_one()
        assert other.category == "people"
        assert other.category_source == "default"

    async def test_apply_to_existing_domain_level(self, db, account_a, user):
        m1 = await _add_message(db, account_a, from_address="alpha@news.com", category="people")
        m2 = await _add_message(db, account_a, from_address="beta@news.com",  category="people")
        m_other = await _add_message(db, account_a, from_address="friend@gmail.com", category="people")
        await db.commit()

        client, app = await _client_with_auth_override(user)
        try:
            r = await client.patch(
                f"/api/messages/{m1.id}/category",
                json={"category": "bulk", "apply_to_domain": True, "apply_to_existing": True},
            )
            assert r.status_code == 200
        finally:
            app.dependency_overrides.clear()
            await client.aclose()

        from sqlalchemy import select
        from app.models.message import Message
        for mid in (m1.id, m2.id):
            row = (await db.execute(select(Message).where(Message.id == mid))).scalar_one()
            assert row.category == "bulk"
            assert row.category_source == "override"
        other = (await db.execute(select(Message).where(Message.id == m_other.id))).scalar_one()
        # Different domain — must not be touched.
        assert other.category == "people"

    async def test_403_for_other_users_message(self, db, account_a, user, other_user):
        m = await _add_message(db, account_a, from_address="x@y.com", category="people")
        await db.commit()

        # Authenticate as a *different* user.
        client, app = await _client_with_auth_override(other_user)
        try:
            r = await client.patch(
                f"/api/messages/{m.id}/category",
                json={"category": "bulk", "apply_to_domain": False, "apply_to_existing": False},
            )
            # The handler uses _get_message_or_404 which scopes to the
            # caller's accounts, so the response is 404 (we don't leak
            # existence). Spec says 403; matching the existing helper
            # behaviour is the correct convention here — note as such.
            assert r.status_code == 404
        finally:
            app.dependency_overrides.clear()
            await client.aclose()
