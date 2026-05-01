"""
People/Bulk classification.

Pure function: runs the priority gauntlet (override → reply history →
header rules → default) and returns (category, source). Does NOT write to
messages or sender_classifications — caller is responsible for persistence.

Gauntlet (stop at the first match):

    1. Override — sender_classifications row scoped to the account, keyed
       on sender_address (address-level wins) or sender_domain (domain-
       level fallback). Source: 'override'.

    2. Reply history — has the user (across ANY of their accounts) ever
       sent a message whose to_addresses or cc_addresses contains this
       sender's address? Skips bcc. Source: 'history'.

    3. Header rules — any one of: List-Unsubscribe, List-ID, Precedence:
       bulk|list, Auto-Submitted (anything but 'no'), Content-Type
       text/calendar, multipart/report (DSN), mailer-daemon@ /
       postmaster@ pattern, From-domain or Return-Path on KNOWN_ESP_DOMAINS
       (subdomain match included). Source: 'headers' → category 'bulk'.

    4. Default → ('people', 'default').

Data invariants (Phase 8 onward):
  - All addresses (Message.from_address, the .address field of every
    JSONB list-of-objects column, sender_classifications.sender_address)
    are stored lowercased + stripped at write time. Five ingest paths +
    the EmailAddress Pydantic validator enforce this. Migration 010
    backfilled legacy rows.
  - Despite the above, this module still lowercases on BOTH sides at
    query time. Ingest normalization is best-effort; defensive lookups
    survive a future regression.

Limitation:
  - Classifier-relevant headers (List-Unsubscribe, List-ID, Precedence,
    Auto-Submitted) are NOT persisted on messages. The classifier reads
    them from the local headers dict at sync time, classifies, and
    discards them. Bulk re-classification of historical mail therefore
    can only apply the from-address-only subset of the header gauntlet.
    See docs/people_bulk.md and the backfill script for details.

Cross-account scope:
  - Reply history is USER-scoped — a reply from work account counts as
    a People signal for mail arriving on personal account.
  - Overrides are ACCOUNT-scoped — work and personal can disagree about
    the same sender. By design.
"""
from __future__ import annotations

import logging
import uuid
from typing import Literal, Optional

from sqlalchemy import and_, exists, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.message import Message
from app.models.sender_classification import SenderClassification

logger = logging.getLogger(__name__)


Category = Literal["people", "bulk"]
Source = Literal["override", "history", "headers", "default"]


# ---------------------------------------------------------------------------
# ESP domain list
# ---------------------------------------------------------------------------
# Matches the FULL domain or any parent (so foo.mailgun.org matches
# mailgun.org). Intentionally easy to extend — drop new entries below.
KNOWN_ESP_DOMAINS: frozenset[str] = frozenset({
    "mailchimp.com", "mcsv.net",
    "mailgun.org", "mailgun.net",
    "sendgrid.net", "sendgrid.com",
    "klaviyo.com", "klaviyomail.com",
    "hubspot.com", "hubspotemail.net", "hs-sites.com",
    "constantcontact.com", "ccsend.com",
    "postmarkapp.com", "pmsrvr.com",
    "amazonses.com",
    "customer.io",
    "iterable.com",
    "activehosted.com",
    "convertkit.com", "convertkit-mail.com",
    "substack.com",
    "beehiiv.com",
    "ghost.io",
    "buttondown.email",
    "marketo.com", "marketo.net", "mktomail.com",
    "pardot.com", "pardotemail.com",
    "braze.com", "braze.eu",
    "drip.com", "getdrip.com",
    "sendinblue.com", "sib-emails.com",
    "brevo.com",
})


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _domain_of(address: str) -> Optional[str]:
    """Return the lowercased domain part of an email address, or None."""
    if not address or "@" not in address:
        return None
    return address.rsplit("@", 1)[-1].strip().lower() or None


def _ci_get(headers: dict, name: str) -> Optional[str]:
    """Case-insensitive header lookup. Returns the raw value or None."""
    if not headers:
        return None
    target = name.lower()
    for k, v in headers.items():
        if k and k.lower() == target:
            return v
    return None


def _is_known_esp_domain(domain: Optional[str]) -> bool:
    """True if `domain` equals or is a subdomain of any KNOWN_ESP_DOMAINS entry."""
    if not domain:
        return False
    domain = domain.lower().strip(".")
    if domain in KNOWN_ESP_DOMAINS:
        return True
    # Subdomain match: walk parents.
    parts = domain.split(".")
    for i in range(1, len(parts) - 1):
        parent = ".".join(parts[i:])
        if parent in KNOWN_ESP_DOMAINS:
            return True
    return False


def _return_path_address(headers: dict) -> Optional[str]:
    """Extract the bare address from a Return-Path: <addr@example.com> header."""
    raw = _ci_get(headers, "return-path")
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("<") and raw.endswith(">"):
        raw = raw[1:-1]
    return raw.strip().lower() or None


# ---------------------------------------------------------------------------
# Reply-history helper (the JSONB-containment SQL recon §4 said didn't exist)
# ---------------------------------------------------------------------------

def address_in_recipients(addr_lower: str):
    """
    Build a SQLAlchemy WHERE clause that is True iff `addr_lower` (already
    lowercased) appears in the lowercased `to_addresses` OR `cc_addresses`
    JSONB column on the `messages` row currently being filtered.

    Postgres-only (uses jsonb_array_elements). Skips bcc_addresses
    intentionally — bcc on sent items is unreliable, and Phase 2 spec
    excludes it.
    """
    elt_to = func.jsonb_array_elements(Message.to_addresses).table_valued("value")
    elt_cc = func.jsonb_array_elements(Message.cc_addresses).table_valued("value")

    in_to = exists(
        select(literal(1))
        .select_from(elt_to)
        .where(func.lower(elt_to.c.value.op("->>")("address")) == addr_lower)
    )
    in_cc = exists(
        select(literal(1))
        .select_from(elt_cc)
        .where(func.lower(elt_cc.c.value.op("->>")("address")) == addr_lower)
    )
    return in_to | in_cc


# ---------------------------------------------------------------------------
# Gauntlet steps
# ---------------------------------------------------------------------------

async def _check_override(
    db: AsyncSession,
    account_id: uuid.UUID,
    sender_address_lower: str,
    sender_domain_lower: Optional[str],
) -> Optional[Category]:
    """Returns the override category if a rule exists, else None."""
    # Address-level rule wins over domain-level — query for it first.
    addr_row = await db.execute(
        select(SenderClassification.category).where(
            and_(
                SenderClassification.account_id == account_id,
                SenderClassification.is_domain_rule.is_(False),
                func.lower(SenderClassification.sender_address) == sender_address_lower,
            )
        ).limit(1)
    )
    cat = addr_row.scalar_one_or_none()
    if cat:
        return cat  # type: ignore[return-value]

    if sender_domain_lower:
        dom_row = await db.execute(
            select(SenderClassification.category).where(
                and_(
                    SenderClassification.account_id == account_id,
                    SenderClassification.is_domain_rule.is_(True),
                    func.lower(SenderClassification.sender_domain) == sender_domain_lower,
                )
            ).limit(1)
        )
        cat = dom_row.scalar_one_or_none()
        if cat:
            return cat  # type: ignore[return-value]

    return None


async def _check_reply_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    sender_address_lower: str,
) -> bool:
    """
    True if the user has ever sent a message (across ANY of their accounts)
    where this sender's address was in to_addresses or cc_addresses.
    """
    if not sender_address_lower:
        return False

    q = (
        select(literal(1))
        .select_from(Message)
        .join(Account, Account.id == Message.account_id)
        .where(
            Account.user_id == user_id,
            Message.is_sent.is_(True),
            address_in_recipients(sender_address_lower),
        )
        .limit(1)
    )
    row = await db.execute(q)
    return row.first() is not None


def _check_header_rules(
    headers: dict,
    content_type: Optional[str],
    from_address_lower: str,
) -> bool:
    """True if any header rule fires → message is Bulk."""
    # 1. List-Unsubscribe
    if _ci_get(headers, "list-unsubscribe"):
        return True
    # 2. List-ID
    if _ci_get(headers, "list-id"):
        return True
    # 3. Precedence: bulk | list
    prec = _ci_get(headers, "precedence")
    if prec and prec.strip().lower() in {"bulk", "list"}:
        return True
    # 4. Auto-Submitted: anything other than 'no'
    auto = _ci_get(headers, "auto-submitted")
    if auto and auto.strip().lower() != "no":
        return True
    # 5. text/calendar
    ct = (content_type or _ci_get(headers, "content-type") or "").strip().lower()
    if ct.startswith("text/calendar"):
        return True
    # 6. DSN / bounce — multipart/report content type, or mailer-daemon /
    #    postmaster sender pattern.
    if "multipart/report" in ct:
        return True
    local = from_address_lower.split("@", 1)[0] if "@" in from_address_lower else ""
    if local in {"mailer-daemon", "postmaster"}:
        return True
    # 7. ESP domain match — From or Return-Path.
    from_domain = _domain_of(from_address_lower)
    if _is_known_esp_domain(from_domain):
        return True
    rp = _return_path_address(headers)
    if rp and _is_known_esp_domain(_domain_of(rp)):
        return True
    return False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def classify_by_headers(
    from_address: str,
    headers: dict,
    content_type: Optional[str] = None,
) -> Optional[tuple[Category, Source]]:
    """
    Pure-Python header/ESP gauntlet step. Returns ('bulk', 'headers') if
    any header rule fires, else None (caller decides the default).

    Reused by the sync-time `classify_message` AND by the offline backfill
    script — backfill skips the override and history DB queries (it
    pre-computes those) but still needs the same header rule logic, so
    extracting this avoids duplication and drift.
    """
    addr_lower = (from_address or "").strip().lower()
    if _check_header_rules(headers or {}, content_type, addr_lower):
        return "bulk", "headers"
    return None


async def classify_message(
    *,
    db: AsyncSession,
    account_id: uuid.UUID,
    user_id: uuid.UUID,
    from_address: str,
    headers: dict,
    content_type: Optional[str] = None,
) -> tuple[Category, Source]:
    """
    Run the priority gauntlet and return (category, source). Pure: no writes.
    """
    addr_lower = (from_address or "").strip().lower()
    domain_lower = _domain_of(addr_lower)

    # 1. Override
    override = await _check_override(db, account_id, addr_lower, domain_lower)
    if override:
        return override, "override"

    # 2. Reply history (cross-account, user-scoped)
    if addr_lower and await _check_reply_history(db, user_id, addr_lower):
        return "people", "history"

    # 3. Header rules
    header_verdict = classify_by_headers(from_address, headers, content_type)
    if header_verdict is not None:
        return header_verdict

    # 4. Default
    return "people", "default"


# ---------------------------------------------------------------------------
# Sync-time wrapper: per-batch cache + safe fallback
# ---------------------------------------------------------------------------

class ClassificationBatch:
    """
    Per-sync-batch classifier wrapper.

    1. Caches results by (from_address.lower(), tuple of relevant header
       fingerprint bits) so that 50 newsletter blasts from the same sender
       in one Gmail backfill cause one DB lookup, not 50.
    2. Catches exceptions from `classify_message` and falls back to
       ('people', 'default') so a single malformed message can't kill the
       entire sync. Logs the failure with remote_id and from_address.

    Caller creates one of these per sync run and calls `classify(...)`
    once per message before `db.add(message)`.
    """

    def __init__(self, db: AsyncSession, account_id: uuid.UUID, user_id: uuid.UUID):
        self._db = db
        self._account_id = account_id
        self._user_id = user_id
        # Keyed by from_address only — overrides and reply history are
        # sender-keyed and don't depend on the message-specific headers.
        # Header rules can flip the result for the same sender across
        # messages (e.g. one personal reply, one newsletter via the same
        # mailbox), so cache only when result is sourced from override
        # or history (sender-stable). Header/default results bypass the
        # cache. See _cache_if_stable below.
        self._cache: dict[str, tuple[Category, Source]] = {}

    async def classify(
        self,
        *,
        from_address: str,
        headers: dict,
        content_type: Optional[str],
        remote_id: Optional[str] = None,
    ) -> tuple[Category, Source]:
        addr_lower = (from_address or "").strip().lower()

        # Fast-path: cached sender-stable result.
        cached = self._cache.get(addr_lower)
        if cached is not None:
            return cached

        try:
            result = await classify_message(
                db=self._db,
                account_id=self._account_id,
                user_id=self._user_id,
                from_address=from_address,
                headers=headers or {},
                content_type=content_type,
            )
        except Exception as e:
            logger.exception(
                "Classifier failed for remote_id=%s from=%s: %s — using default",
                remote_id, from_address, e,
            )
            return "people", "default"

        # Only cache results whose verdict doesn't depend on per-message
        # headers — otherwise we'd misclassify a different message from
        # the same sender. Override and history are sender-stable.
        if result[1] in ("override", "history"):
            self._cache[addr_lower] = result
        return result
