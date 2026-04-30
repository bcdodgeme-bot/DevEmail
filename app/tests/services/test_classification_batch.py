"""
Tests for the per-sync-batch classifier wrapper that the sync hot path uses.
Pure-Python: classifier is monkey-patched, no real DB needed.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.services import classification as classification_module
from app.services.classification import ClassificationBatch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_batch():
    db = MagicMock(name="db")
    return ClassificationBatch(
        db=db,
        account_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )


class _Counter:
    """Async stub for classify_message that records calls and returns
    a configured result. Lets us assert call count + arg shapes."""

    def __init__(self, returns):
        self.returns = returns
        self.calls: list[dict] = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.returns, Exception):
            raise self.returns
        # If `returns` is a list, pop one per call so different calls
        # can return different verdicts.
        if isinstance(self.returns, list):
            return self.returns.pop(0)
        return self.returns


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPassthroughArgs:
    async def test_calls_classify_message_with_correct_args(self, monkeypatch):
        stub = _Counter(returns=("people", "default"))
        monkeypatch.setattr(classification_module, "classify_message", stub)

        batch = _make_batch()
        result = await batch.classify(
            from_address="Bob@Example.COM",
            headers={"List-Unsubscribe": "<x>"},
            content_type="text/html",
            remote_id="abc123",
        )

        assert result == ("people", "default")
        assert len(stub.calls) == 1
        call = stub.calls[0]
        assert call["from_address"] == "Bob@Example.COM"
        assert call["headers"] == {"List-Unsubscribe": "<x>"}
        assert call["content_type"] == "text/html"
        # account_id and user_id come from the batch ctor
        assert call["account_id"] == batch._account_id
        assert call["user_id"] == batch._user_id


class TestSafeFallback:
    async def test_classifier_exception_falls_back_to_default(self, monkeypatch, caplog):
        stub = _Counter(returns=RuntimeError("boom"))
        monkeypatch.setattr(classification_module, "classify_message", stub)

        batch = _make_batch()
        with caplog.at_level("ERROR"):
            result = await batch.classify(
                from_address="x@y.com",
                headers={},
                content_type=None,
                remote_id="msg-1",
            )

        assert result == ("people", "default")
        assert any("Classifier failed" in r.message for r in caplog.records)
        # remote_id and from_address should appear in the log for debugging.
        assert any("msg-1" in r.message for r in caplog.records)


class TestBatchCache:
    async def test_override_result_cached_within_batch(self, monkeypatch):
        stub = _Counter(returns=("bulk", "override"))
        monkeypatch.setattr(classification_module, "classify_message", stub)

        batch = _make_batch()
        r1 = await batch.classify(
            from_address="newsletter@x.com",
            headers={"List-Unsubscribe": "<x>"},
            content_type=None,
        )
        r2 = await batch.classify(
            from_address="newsletter@x.com",
            headers={},  # different headers
            content_type=None,
        )

        assert r1 == r2 == ("bulk", "override")
        # Cached after first call → second call must NOT invoke classify_message.
        assert len(stub.calls) == 1

    async def test_history_result_cached_within_batch(self, monkeypatch):
        stub = _Counter(returns=("people", "history"))
        monkeypatch.setattr(classification_module, "classify_message", stub)

        batch = _make_batch()
        await batch.classify(from_address="a@b.com", headers={}, content_type=None)
        await batch.classify(from_address="a@b.com", headers={}, content_type=None)
        await batch.classify(from_address="A@B.COM", headers={}, content_type=None)

        # All three are the same sender (case-insensitive). One real call.
        assert len(stub.calls) == 1

    async def test_header_result_NOT_cached(self, monkeypatch):
        # Header verdicts depend on per-message headers, so the same sender
        # could be people on one message and bulk on another. Don't cache.
        stub = _Counter(returns=[
            ("bulk", "headers"),
            ("bulk", "headers"),
        ])
        monkeypatch.setattr(classification_module, "classify_message", stub)

        batch = _make_batch()
        await batch.classify(from_address="a@b.com", headers={"List-ID": "<x>"}, content_type=None)
        await batch.classify(from_address="a@b.com", headers={"List-ID": "<x>"}, content_type=None)

        assert len(stub.calls) == 2  # not cached

    async def test_default_result_NOT_cached(self, monkeypatch):
        stub = _Counter(returns=[
            ("people", "default"),
            ("people", "default"),
        ])
        monkeypatch.setattr(classification_module, "classify_message", stub)

        batch = _make_batch()
        await batch.classify(from_address="a@b.com", headers={}, content_type=None)
        await batch.classify(from_address="a@b.com", headers={}, content_type=None)

        # Default isn't sender-stable either (a future override or reply
        # could flip the verdict), so don't cache.
        assert len(stub.calls) == 2

    async def test_different_senders_each_get_their_own_call(self, monkeypatch):
        stub = _Counter(returns=[
            ("bulk", "override"),
            ("people", "history"),
            ("people", "history"),
        ])
        monkeypatch.setattr(classification_module, "classify_message", stub)

        batch = _make_batch()
        await batch.classify(from_address="a@x.com", headers={}, content_type=None)
        await batch.classify(from_address="b@x.com", headers={}, content_type=None)
        # repeat b
        await batch.classify(from_address="b@x.com", headers={}, content_type=None)

        # a once, b once (cached on second call), c never. Total = 2.
        assert len(stub.calls) == 2
