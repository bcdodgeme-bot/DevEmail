"""
Tests for the People/Bulk classifier (app/services/classification.py).

Pure-Python tests (header rules, ESP matching, helpers) run anywhere.
DB-bound tests (override, reply history, gauntlet priority) require
TEST_DATABASE_URL pointing at a Postgres instance and are skipped otherwise.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.account import Account
from app.models.message import Message
from app.models.sender_classification import SenderClassification
from app.services.classification import (
    KNOWN_ESP_DOMAINS,
    _check_header_rules,
    _domain_of,
    _is_known_esp_domain,
    classify_message,
)
from app.tests.conftest import requires_db


# ---------------------------------------------------------------------------
# Pure-Python: helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_domain_of_lowercases(self):
        assert _domain_of("Foo@Example.COM") == "example.com"

    def test_domain_of_handles_no_at(self):
        assert _domain_of("not-an-email") is None
        assert _domain_of("") is None

    def test_known_esp_full_match(self):
        assert _is_known_esp_domain("amazonses.com")

    def test_known_esp_subdomain(self):
        assert _is_known_esp_domain("us-east-1.amazonses.com")
        assert _is_known_esp_domain("foo.bar.mailgun.org")

    def test_known_esp_negative(self):
        assert not _is_known_esp_domain("example.com")
        assert not _is_known_esp_domain(None)
        assert not _is_known_esp_domain("")

    def test_known_esp_does_not_match_suffix_collision(self):
        # 'sescom.com' must not match 'amazonses.com'
        assert not _is_known_esp_domain("sescom.com")
        # 'evilmailgun.org' must not match 'mailgun.org'
        assert not _is_known_esp_domain("evilmailgun.org")

    def test_esp_set_has_all_required_entries(self):
        # Sanity check the spec-listed entries are present.
        for d in [
            "mailchimp.com", "sendgrid.net", "klaviyo.com", "hubspot.com",
            "amazonses.com", "substack.com", "mailgun.org", "marketo.com",
            "braze.com", "brevo.com",
        ]:
            assert d in KNOWN_ESP_DOMAINS


# ---------------------------------------------------------------------------
# Pure-Python: header rules
# ---------------------------------------------------------------------------

class TestHeaderRules:
    def test_list_unsubscribe_triggers_bulk(self):
        assert _check_header_rules(
            {"List-Unsubscribe": "<https://x.example/u>"}, None, "a@b.com"
        )

    def test_list_id_triggers_bulk(self):
        assert _check_header_rules({"List-ID": "<list.example.com>"}, None, "a@b.com")

    def test_precedence_bulk_triggers(self):
        assert _check_header_rules({"Precedence": "bulk"}, None, "a@b.com")

    def test_precedence_list_triggers(self):
        assert _check_header_rules({"Precedence": "LIST"}, None, "a@b.com")

    def test_precedence_other_does_not_trigger(self):
        assert not _check_header_rules({"Precedence": "first-class"}, None, "a@b.com")

    def test_auto_submitted_auto_replied_triggers(self):
        assert _check_header_rules(
            {"Auto-Submitted": "auto-replied"}, None, "a@b.com"
        )

    def test_auto_submitted_no_does_not_trigger(self):
        assert not _check_header_rules({"Auto-Submitted": "no"}, None, "a@b.com")
        assert not _check_header_rules({"Auto-Submitted": "NO"}, None, "a@b.com")

    def test_text_calendar_content_type_triggers(self):
        assert _check_header_rules({}, "text/calendar; method=REQUEST", "a@b.com")

    def test_text_calendar_via_header_triggers(self):
        assert _check_header_rules(
            {"Content-Type": "text/calendar; method=REQUEST"}, None, "a@b.com"
        )

    def test_dsn_multipart_report_triggers(self):
        assert _check_header_rules(
            {}, "multipart/report; report-type=delivery-status", "x@y.com"
        )

    def test_mailer_daemon_triggers(self):
        assert _check_header_rules({}, None, "mailer-daemon@gmail.com")

    def test_postmaster_triggers(self):
        assert _check_header_rules({}, None, "postmaster@gmail.com")

    def test_esp_from_domain_triggers(self):
        assert _check_header_rules({}, None, "noreply@amazonses.com")

    def test_esp_from_subdomain_triggers(self):
        assert _check_header_rules({}, None, "noreply@us-east-1.amazonses.com")

    def test_esp_via_return_path(self):
        # Return-Path on a known ESP triggers even when From is benign-looking.
        assert _check_header_rules(
            {"Return-Path": "<bounce@bounce.mcsv.net>"},
            None,
            "newsletter@somecompany.com",
        )
        assert _check_header_rules(
            {"Return-Path": "<bounce@mailgun.org>"},
            None,
            "hi@somecompany.com",
        )

    def test_header_lookup_is_case_insensitive(self):
        assert _check_header_rules(
            {"list-unsubscribe": "<x>"}, None, "a@b.com"
        )
        assert _check_header_rules(
            {"LIST-UNSUBSCRIBE": "<x>"}, None, "a@b.com"
        )

    def test_no_match_returns_false(self):
        assert not _check_header_rules(
            {"From": "Alice <alice@example.com>"},
            "text/html",
            "alice@example.com",
        )


# ---------------------------------------------------------------------------
# DB-bound: override, reply history, gauntlet priority
# ---------------------------------------------------------------------------

@requires_db
class TestOverride:
    async def test_address_level_override_wins(self, db, account_a, user):
        db.add(SenderClassification(
            account_id=account_a.id,
            sender_address="alice@example.com",
            sender_domain=None,
            is_domain_rule=False,
            category="bulk",
            learned_from="manual_move",
        ))
        await db.flush()

        cat, src = await classify_message(
            db=db, account_id=account_a.id, user_id=user.id,
            from_address="Alice@Example.COM",
            headers={}, content_type=None,
        )
        assert (cat, src) == ("bulk", "override")

    async def test_address_level_beats_domain_level(self, db, account_a, user):
        # Address rule says people, domain rule says bulk → address wins.
        db.add(SenderClassification(
            account_id=account_a.id,
            sender_address="alice@example.com",
            sender_domain=None,
            is_domain_rule=False,
            category="people",
            learned_from="manual_move",
        ))
        db.add(SenderClassification(
            account_id=account_a.id,
            sender_address="*@example.com",
            sender_domain="example.com",
            is_domain_rule=True,
            category="bulk",
            learned_from="manual_move",
        ))
        await db.flush()

        cat, src = await classify_message(
            db=db, account_id=account_a.id, user_id=user.id,
            from_address="alice@example.com",
            headers={}, content_type=None,
        )
        assert (cat, src) == ("people", "override")

    async def test_domain_level_when_no_address_rule(self, db, account_a, user):
        db.add(SenderClassification(
            account_id=account_a.id,
            sender_address="*@example.com",
            sender_domain="example.com",
            is_domain_rule=True,
            category="bulk",
            learned_from="manual_settings",
        ))
        await db.flush()

        cat, src = await classify_message(
            db=db, account_id=account_a.id, user_id=user.id,
            from_address="anyone@Example.com",
            headers={}, content_type=None,
        )
        assert (cat, src) == ("bulk", "override")

    async def test_override_is_account_scoped(self, db, account_a, account_b, user):
        # Override on account_a should NOT affect account_b.
        db.add(SenderClassification(
            account_id=account_a.id,
            sender_address="alice@example.com",
            sender_domain=None,
            is_domain_rule=False,
            category="bulk",
            learned_from="manual_move",
        ))
        await db.flush()

        cat, src = await classify_message(
            db=db, account_id=account_b.id, user_id=user.id,
            from_address="alice@example.com",
            headers={}, content_type=None,
        )
        # No override for account_b, no history, no headers → default
        assert (cat, src) == ("people", "default")


@requires_db
class TestReplyHistory:
    async def _add_sent(
        self, db, account, *, to_addresses=None, cc_addresses=None, bcc_addresses=None,
    ):
        msg = Message(
            id=uuid.uuid4(),
            thread_id=None,  # nullable=False — we'll create a thread
            account_id=account.id,
            from_address=account.email_address,
            to_addresses=to_addresses or [],
            cc_addresses=cc_addresses or [],
            bcc_addresses=bcc_addresses or [],
            is_sent=True,
            subject="hi",
        )
        # thread_id is nullable=False; create an inline thread.
        from app.models.thread import Thread
        t = Thread(id=uuid.uuid4(), user_id=account.user_id, message_count=1)
        db.add(t)
        await db.flush()
        msg.thread_id = t.id
        db.add(msg)
        await db.flush()

    async def test_hit_via_to_addresses(self, db, account_a, user):
        await self._add_sent(
            db, account_a,
            to_addresses=[{"name": "Bob", "address": "bob@example.com"}],
        )
        cat, src = await classify_message(
            db=db, account_id=account_a.id, user_id=user.id,
            from_address="bob@example.com",
            headers={}, content_type=None,
        )
        assert (cat, src) == ("people", "history")

    async def test_hit_via_cc_addresses(self, db, account_a, user):
        await self._add_sent(
            db, account_a,
            to_addresses=[{"name": "X", "address": "x@example.com"}],
            cc_addresses=[{"name": "Carol", "address": "carol@example.com"}],
        )
        cat, src = await classify_message(
            db=db, account_id=account_a.id, user_id=user.id,
            from_address="carol@example.com",
            headers={}, content_type=None,
        )
        assert (cat, src) == ("people", "history")

    async def test_bcc_match_does_NOT_classify_people(self, db, account_a, user):
        await self._add_sent(
            db, account_a,
            to_addresses=[{"name": "X", "address": "x@example.com"}],
            bcc_addresses=[{"name": "Hidden", "address": "hidden@example.com"}],
        )
        cat, src = await classify_message(
            db=db, account_id=account_a.id, user_id=user.id,
            from_address="hidden@example.com",
            headers={}, content_type=None,
        )
        # No header rules fire, no override → default people. Source must NOT
        # be 'history' — bcc must not count.
        assert src == "default"

    async def test_case_insensitive_both_sides(self, db, account_a, user):
        await self._add_sent(
            db, account_a,
            to_addresses=[{"name": "Alice", "address": "ALICE@FOO.COM"}],
        )
        cat, src = await classify_message(
            db=db, account_id=account_a.id, user_id=user.id,
            from_address="alice@foo.com",
            headers={}, content_type=None,
        )
        assert (cat, src) == ("people", "history")

    async def test_user_scoped_not_account_scoped(
        self, db, account_a, account_b, user,
    ):
        # Sent from account_a; incoming on account_b. Same user.
        await self._add_sent(
            db, account_a,
            to_addresses=[{"name": "Dave", "address": "dave@example.com"}],
        )
        cat, src = await classify_message(
            db=db, account_id=account_b.id, user_id=user.id,
            from_address="dave@example.com",
            headers={}, content_type=None,
        )
        assert (cat, src) == ("people", "history")

    async def test_other_users_history_does_not_leak(
        self, db, account_a, user, other_user,
    ):
        # Build a separate account owned by other_user with sent history.
        from app.tests.conftest import _make_account
        other_account = await _make_account(
            db, other_user.id, email="other@test.local"
        )
        await self._add_sent(
            db, other_account,
            to_addresses=[{"name": "Eve", "address": "eve@example.com"}],
        )
        cat, src = await classify_message(
            db=db, account_id=account_a.id, user_id=user.id,
            from_address="eve@example.com",
            headers={}, content_type=None,
        )
        # user has no history with eve — should not be people/history.
        assert src == "default"


@requires_db
class TestGauntletPriority:
    async def test_override_beats_history(self, db, account_a, user):
        # Build sent history (would otherwise classify as people/history).
        await TestReplyHistory()._add_sent(
            db, account_a,
            to_addresses=[{"name": "Z", "address": "z@example.com"}],
        )
        # Then add an override to bulk.
        db.add(SenderClassification(
            account_id=account_a.id,
            sender_address="z@example.com",
            sender_domain=None,
            is_domain_rule=False,
            category="bulk",
            learned_from="manual_move",
        ))
        await db.flush()

        cat, src = await classify_message(
            db=db, account_id=account_a.id, user_id=user.id,
            from_address="z@example.com",
            headers={}, content_type=None,
        )
        assert (cat, src) == ("bulk", "override")

    async def test_override_beats_headers(self, db, account_a, user):
        # ESP domain in From would normally fire headers/bulk. Override to people.
        db.add(SenderClassification(
            account_id=account_a.id,
            sender_address="hi@amazonses.com",
            sender_domain=None,
            is_domain_rule=False,
            category="people",
            learned_from="manual_move",
        ))
        await db.flush()

        cat, src = await classify_message(
            db=db, account_id=account_a.id, user_id=user.id,
            from_address="hi@amazonses.com",
            headers={"List-Unsubscribe": "<x>"},  # also a bulk signal
            content_type=None,
        )
        assert (cat, src) == ("people", "override")

    async def test_history_beats_headers(self, db, account_a, user):
        # User has replied to this address before — even if From is on an ESP.
        await TestReplyHistory()._add_sent(
            db, account_a,
            to_addresses=[{"name": "X", "address": "support@amazonses.com"}],
        )
        cat, src = await classify_message(
            db=db, account_id=account_a.id, user_id=user.id,
            from_address="support@amazonses.com",
            headers={"List-Unsubscribe": "<x>"},
            content_type=None,
        )
        assert (cat, src) == ("people", "history")

    async def test_default_when_nothing_matches(self, db, account_a, user):
        cat, src = await classify_message(
            db=db, account_id=account_a.id, user_id=user.id,
            from_address="nobody@unknown.example",
            headers={"From": "Nobody <nobody@unknown.example>"},
            content_type="text/html",
        )
        assert (cat, src) == ("people", "default")
