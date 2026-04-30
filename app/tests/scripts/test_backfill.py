"""
Tests for the backfill script.

Pure-Python tests cover the per-message verdict logic (no DB needed).
DB-bound tests cover the end-to-end behavior (replied-to set, batched
UPDATEs, --user-id scoping, dry-run no-write) and skip when
TEST_DATABASE_URL isn't configured.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.scripts.backfill_classifications import (
    backfill_user,
    build_replied_to_set,
    verdict_for_message,
)
from app.tests.conftest import requires_db


def _msg(**kwargs):
    """Mock a Message row with just the fields the verdict logic reads."""
    defaults = dict(
        id=uuid.uuid4(),
        from_address="x@y.com",
        category="people",
        category_source="default",
        subject="t",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Pure-Python: verdict_for_message
# ---------------------------------------------------------------------------

class TestVerdict:
    def test_override_skipped_even_when_other_rules_would_fire(self):
        m = _msg(
            from_address="news@amazonses.com",  # would normally be bulk/headers
            category="people",
            category_source="override",
        )
        assert verdict_for_message(m, replied_to=set()) is None

    def test_reply_history_hits(self):
        m = _msg(from_address="Bob@Example.COM",
                 category="people", category_source="default")
        v = verdict_for_message(m, replied_to={"bob@example.com"})
        assert v == ("people", "history")

    def test_reply_history_already_correct_returns_none(self):
        m = _msg(from_address="bob@x.com",
                 category="people", category_source="history")
        assert verdict_for_message(m, replied_to={"bob@x.com"}) is None

    def test_esp_domain_classifies_bulk(self):
        m = _msg(from_address="noreply@amazonses.com",
                 category="people", category_source="default")
        v = verdict_for_message(m, replied_to=set())
        assert v == ("bulk", "headers")

    def test_esp_subdomain_classifies_bulk(self):
        m = _msg(from_address="noreply@us-east-1.amazonses.com",
                 category="people", category_source="default")
        v = verdict_for_message(m, replied_to=set())
        assert v == ("bulk", "headers")

    def test_mailer_daemon_classifies_bulk(self):
        m = _msg(from_address="mailer-daemon@gmail.com",
                 category="people", category_source="default")
        v = verdict_for_message(m, replied_to=set())
        assert v == ("bulk", "headers")

    def test_default_to_default_is_noop(self):
        # Plain message, no history, no ESP — already ('people', 'default').
        m = _msg(from_address="alice@unknown.example",
                 category="people", category_source="default")
        assert verdict_for_message(m, replied_to=set()) is None

    def test_history_beats_esp(self):
        # User has replied to support@amazonses.com — history wins over
        # the ESP-domain header rule (matching Phase 2 priority).
        m = _msg(from_address="support@amazonses.com",
                 category="people", category_source="default")
        v = verdict_for_message(m, replied_to={"support@amazonses.com"})
        assert v == ("people", "history")

    def test_old_value_drift_triggers_update(self):
        # If a row was somehow in ('bulk', 'default') and rules now say
        # ('people', 'history'), we WRITE.
        m = _msg(from_address="bob@x.com",
                 category="bulk", category_source="default")
        v = verdict_for_message(m, replied_to={"bob@x.com"})
        assert v == ("people", "history")


# ---------------------------------------------------------------------------
# DB-bound: end-to-end
# ---------------------------------------------------------------------------

@requires_db
class TestBuildRepliedToSet:
    async def test_collects_to_and_cc_skips_bcc(self, db, account_a, user):
        from app.models.message import Message
        from app.models.thread import Thread

        t = Thread(id=uuid.uuid4(), user_id=user.id, message_count=1)
        db.add(t); await db.flush()
        db.add(Message(
            id=uuid.uuid4(), thread_id=t.id, account_id=account_a.id,
            is_sent=True,
            to_addresses=[{"address": "ALICE@FOO.com"}],
            cc_addresses=[{"address": "carol@foo.com"}],
            bcc_addresses=[{"address": "hidden@foo.com"}],
            from_address=account_a.email_address,
        ))
        await db.commit()

        addrs = await build_replied_to_set(db, user.id)
        assert "alice@foo.com" in addrs
        assert "carol@foo.com" in addrs
        assert "hidden@foo.com" not in addrs

    async def test_user_scoped_not_account_scoped(
        self, db, account_a, account_b, user,
    ):
        # Sent on account_a should be visible from user.id's perspective.
        from app.models.message import Message
        from app.models.thread import Thread
        t = Thread(id=uuid.uuid4(), user_id=user.id, message_count=1)
        db.add(t); await db.flush()
        db.add(Message(
            id=uuid.uuid4(), thread_id=t.id, account_id=account_a.id,
            is_sent=True,
            to_addresses=[{"address": "dave@x.com"}],
            cc_addresses=[],
            bcc_addresses=[],
            from_address=account_a.email_address,
        ))
        await db.commit()
        addrs = await build_replied_to_set(db, user.id)
        assert "dave@x.com" in addrs

    async def test_other_user_history_does_not_leak(
        self, db, account_a, user, other_user,
    ):
        from app.tests.conftest import _make_account
        from app.models.message import Message
        from app.models.thread import Thread

        other_account = await _make_account(db, other_user.id, email="other@t.local")
        t = Thread(id=uuid.uuid4(), user_id=other_user.id, message_count=1)
        db.add(t); await db.flush()
        db.add(Message(
            id=uuid.uuid4(), thread_id=t.id, account_id=other_account.id,
            is_sent=True,
            to_addresses=[{"address": "eve@x.com"}],
            cc_addresses=[],
            bcc_addresses=[],
            from_address=other_account.email_address,
        ))
        await db.commit()

        # user.id has no history → eve must not appear in user's set.
        addrs = await build_replied_to_set(db, user.id)
        assert "eve@x.com" not in addrs


@requires_db
class TestBackfillRun:
    async def _seed(self, db, account, *, from_address, **flags):
        from app.models.message import Message
        from app.models.thread import Thread
        defaults = dict(category="people", category_source="default",
                        is_sent=False, is_archived=False)
        defaults.update(flags)
        t = Thread(id=uuid.uuid4(), user_id=account.user_id, message_count=1)
        db.add(t); await db.flush()
        m = Message(
            id=uuid.uuid4(), thread_id=t.id, account_id=account.id,
            from_address=from_address,
            to_addresses=[], cc_addresses=[], bcc_addresses=[],
            **defaults,
        )
        db.add(m); await db.flush()
        return m

    async def test_real_run_writes_history_and_headers(self, db, account_a, user):
        # Seed a sent message so history fires for bob.
        from app.models.message import Message
        from app.models.thread import Thread
        ts = Thread(id=uuid.uuid4(), user_id=user.id, message_count=1)
        db.add(ts); await db.flush()
        db.add(Message(
            id=uuid.uuid4(), thread_id=ts.id, account_id=account_a.id,
            is_sent=True,
            to_addresses=[{"address": "bob@x.com"}],
            cc_addresses=[], bcc_addresses=[],
            from_address=account_a.email_address,
        ))

        bob_msg  = await self._seed(db, account_a, from_address="bob@x.com")
        esp_msg  = await self._seed(db, account_a, from_address="news@amazonses.com")
        plain    = await self._seed(db, account_a, from_address="alice@unknown.example")
        override = await self._seed(db, account_a, from_address="news@amazonses.com",
                                    category="people", category_source="override")
        await db.commit()

        await backfill_user(db, user.id, dry_run=False)

        from sqlalchemy import select
        async def _re(mid):
            return (await db.execute(select(Message).where(Message.id == mid))).scalar_one()

        assert (await _re(bob_msg.id)).category_source == "history"
        assert (await _re(bob_msg.id)).category == "people"
        assert (await _re(esp_msg.id)).category_source == "headers"
        assert (await _re(esp_msg.id)).category == "bulk"
        # plain stays default (no-op)
        assert (await _re(plain.id)).category == "people"
        assert (await _re(plain.id)).category_source == "default"
        # override is preserved
        assert (await _re(override.id)).category_source == "override"

    async def test_dry_run_does_not_write(self, db, account_a, user):
        m = await self._seed(db, account_a, from_address="news@amazonses.com")
        await db.commit()

        await backfill_user(db, user.id, dry_run=True)

        from sqlalchemy import select
        from app.models.message import Message
        row = (await db.execute(select(Message).where(Message.id == m.id))).scalar_one()
        assert row.category == "people"
        assert row.category_source == "default"

    async def test_user_id_scope_does_not_touch_other_users(
        self, db, account_a, user, other_user,
    ):
        from app.tests.conftest import _make_account
        from app.models.message import Message
        from sqlalchemy import select

        other_account = await _make_account(db, other_user.id, email="o@t.local")
        m_other = await self._seed(
            db, other_account, from_address="news@amazonses.com",
        )
        m_self = await self._seed(
            db, account_a, from_address="news@amazonses.com",
        )
        await db.commit()

        await backfill_user(db, user.id, dry_run=False)

        # `user`'s message should be reclassified.
        self_row  = (await db.execute(select(Message).where(Message.id == m_self.id))).scalar_one()
        assert self_row.category_source == "headers"
        # `other_user`'s message must NOT be touched (we only ran for `user`).
        other_row = (await db.execute(select(Message).where(Message.id == m_other.id))).scalar_one()
        assert other_row.category == "people"
        assert other_row.category_source == "default"

    async def test_completes_across_multiple_batches(self, db, account_a, user):
        """
        Regression: production run died after the first 500-row commit
        because the streaming cursor was killed by commit. Keyset
        pagination must span as many pages as needed without losing the
        cursor state.

        Fixture: 1500 messages — enough to cover three full batches.
        Mix of ESP-domain (should flip to bulk/headers) and plain
        (should stay default, no-op write) so we exercise both the
        update path and the skip path across batch boundaries.
        """
        from app.models.message import Message
        from app.models.thread import Thread
        from sqlalchemy import select

        TOTAL = 1500
        # Bulk-build threads + messages directly to keep the fixture fast.
        thread = Thread(id=uuid.uuid4(), user_id=user.id, message_count=TOTAL)
        db.add(thread)
        await db.flush()

        for i in range(TOTAL):
            db.add(Message(
                id=uuid.uuid4(),
                thread_id=thread.id,
                account_id=account_a.id,
                # Half ESP (will flip to bulk), half plain (no-op).
                from_address=("news@amazonses.com" if i % 2 == 0
                              else f"plain-{i}@unknown.example"),
                to_addresses=[], cc_addresses=[], bcc_addresses=[],
                subject=f"msg-{i}",
                is_read=True, is_sent=False,
                is_archived=False, is_trashed=False,
                category="people", category_source="default",
            ))
        await db.commit()

        await backfill_user(db, user.id, dry_run=False)

        # Every ESP-domain message must now be bulk/headers.
        bulk_count = (await db.execute(
            select(Message).where(
                Message.account_id == account_a.id,
                Message.from_address == "news@amazonses.com",
                Message.category == "bulk",
                Message.category_source == "headers",
            )
        )).scalars().all()
        assert len(bulk_count) == TOTAL // 2, (
            f"Expected {TOTAL // 2} ESP messages to flip to bulk, "
            f"got {len(bulk_count)} — likely a batch was lost mid-run."
        )

        # And the plain ones stay people/default (no-op write skipped).
        plain_count = (await db.execute(
            select(Message).where(
                Message.account_id == account_a.id,
                Message.from_address.like("plain-%@unknown.example"),
                Message.category == "people",
                Message.category_source == "default",
            )
        )).scalars().all()
        assert len(plain_count) == TOTAL // 2
