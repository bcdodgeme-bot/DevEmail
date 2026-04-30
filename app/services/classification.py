"""
People/Bulk classification.

Pure function: runs the priority gauntlet (override → reply history →
header rules → default) and returns (category, source). Does NOT write to
messages or sender_classifications — caller is responsible for persistence.

Address normalization at ingest is currently inconsistent (see
docs/phase2_recon.md). This module lowercases on BOTH sides at query time
and never assumes ingest has normalized.
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from sqlalchemy import and_, exists, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.message import Message
from app.models.sender_classification import SenderClassification


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
    if _check_header_rules(headers or {}, content_type, addr_lower):
        return "bulk", "headers"

    # 4. Default
    return "people", "default"
