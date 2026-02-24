"""
Contact Scoring Service

Computes a relationship score (0–100) for each contact based on:
- Email frequency (sent + received)
- Recency of last interaction
- Reciprocity (two-way vs one-way)
- Thread engagement (replies within threads)

Assigns segment (VIP, Active, Occasional, Cold, Dormant)
and stage (Lead, Prospect, Active, Lapsed) based on score.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, and_, or_, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.message import Message
from app.models.account import Account

logger = logging.getLogger(__name__)

# Scoring weights
WEIGHT_FREQUENCY = 0.30
WEIGHT_RECENCY = 0.35
WEIGHT_RECIPROCITY = 0.20
WEIGHT_VOLUME = 0.15

# Segment thresholds
SEGMENTS = [
    (80, "VIP"),
    (60, "Active"),
    (35, "Occasional"),
    (15, "Cold"),
    (0, "Dormant"),
]

# Stage thresholds (based on recency)
STAGE_DAYS = [
    (14, "Active"),
    (60, "Prospect"),
    (180, "Lapsed"),
    (9999, "Dormant"),
]


class ContactScoringService:
    """Compute relationship scores for contacts."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def score_all_contacts(self, user_id: str) -> int:
        """Score all contacts for a user. Returns count of contacts scored."""
        # Get all user's email accounts
        acct_result = await self.db.execute(
            select(Account.id, Account.email_address).where(Account.user_id == user_id)
        )
        accounts = acct_result.all()
        if not accounts:
            return 0

        account_ids = [a.id for a in accounts]
        user_emails = {a.email_address.lower() for a in accounts}

        # Get all contacts
        contact_result = await self.db.execute(
            select(Contact).where(Contact.user_id == user_id)
        )
        contacts = contact_result.scalars().all()

        now = datetime.now(timezone.utc)
        scored = 0

        for contact in contacts:
            contact_emails = _get_contact_emails(contact)
            if not contact_emails:
                continue

            stats = await self._get_interaction_stats(
                account_ids, user_emails, contact_emails, now
            )

            score = self._compute_score(stats, now)
            segment = _score_to_segment(score)
            stage = _recency_to_stage(stats.get("last_interaction_at"), now)

            contact.score = score
            contact.segment = segment
            contact.stage = stage

            if stats.get("last_interaction_at"):
                contact.last_interaction_at = stats["last_interaction_at"]
                contact.last_interaction_type = stats.get("last_interaction_type", "email")
            if stats.get("first_interaction_at"):
                contact.first_interaction_at = stats["first_interaction_at"]
                contact.first_interaction_type = "email"

            scored += 1

        await self.db.commit()
        logger.info(f"Scored {scored} contacts for user {user_id}")
        return scored

    async def score_single_contact(self, user_id: str, contact_id: str) -> Optional[dict]:
        """Score a single contact and return the result."""
        acct_result = await self.db.execute(
            select(Account.id, Account.email_address).where(Account.user_id == user_id)
        )
        accounts = acct_result.all()
        if not accounts:
            return None

        account_ids = [a.id for a in accounts]
        user_emails = {a.email_address.lower() for a in accounts}

        contact_result = await self.db.execute(
            select(Contact).where(
                Contact.id == contact_id, Contact.user_id == user_id
            )
        )
        contact = contact_result.scalar_one_or_none()
        if not contact:
            return None

        contact_emails = _get_contact_emails(contact)
        if not contact_emails:
            return {"score": 0, "segment": "Dormant", "stage": "Dormant"}

        now = datetime.now(timezone.utc)
        stats = await self._get_interaction_stats(
            account_ids, user_emails, contact_emails, now
        )

        score = self._compute_score(stats, now)
        segment = _score_to_segment(score)
        stage = _recency_to_stage(stats.get("last_interaction_at"), now)

        contact.score = score
        contact.segment = segment
        contact.stage = stage
        if stats.get("last_interaction_at"):
            contact.last_interaction_at = stats["last_interaction_at"]
        if stats.get("first_interaction_at"):
            contact.first_interaction_at = stats["first_interaction_at"]

        await self.db.commit()

        return {
            "score": score,
            "segment": segment,
            "stage": stage,
            "sent_count": stats.get("sent_count", 0),
            "received_count": stats.get("received_count", 0),
            "last_interaction_at": stats.get("last_interaction_at"),
        }

    async def _get_interaction_stats(
        self,
        account_ids: list,
        user_emails: set[str],
        contact_emails: set[str],
        now: datetime,
    ) -> dict:
        """Gather email interaction stats for a contact."""
        # Messages FROM this contact (received)
        received_result = await self.db.execute(
            select(
                func.count(Message.id),
                func.max(Message.received_at),
                func.min(Message.received_at),
            ).where(
                Message.account_id.in_(account_ids),
                func.lower(Message.from_address).in_(contact_emails),
            )
        )
        received_row = received_result.one()
        received_count = received_row[0] or 0
        last_received = received_row[1]
        first_received = received_row[2]

        # Messages TO this contact (sent)
        # We need to check to_addresses JSONB for the contact's email
        sent_count = 0
        last_sent = None
        first_sent = None

        for email_addr in contact_emails:
            sent_result = await self.db.execute(
                select(
                    func.count(Message.id),
                    func.max(Message.sent_at),
                    func.min(Message.sent_at),
                ).where(
                    Message.account_id.in_(account_ids),
                    Message.is_sent == True,
                    Message.to_addresses.cast(text("TEXT")).ilike(f"%{email_addr}%"),
                )
            )
            row = sent_result.one()
            sent_count += row[0] or 0
            if row[1] and (not last_sent or row[1] > last_sent):
                last_sent = row[1]
            if row[2] and (not first_sent or row[2] < first_sent):
                first_sent = row[2]

        # Recent activity (last 90 days)
        cutoff_90 = now - timedelta(days=90)
        recent_result = await self.db.execute(
            select(func.count(Message.id)).where(
                Message.account_id.in_(account_ids),
                func.lower(Message.from_address).in_(contact_emails),
                Message.received_at >= cutoff_90,
            )
        )
        recent_received = recent_result.scalar() or 0

        # Determine last interaction
        last_interaction_at = None
        last_interaction_type = None
        if last_received and last_sent:
            if last_received >= last_sent:
                last_interaction_at = last_received
                last_interaction_type = "email_received"
            else:
                last_interaction_at = last_sent
                last_interaction_type = "email_sent"
        elif last_received:
            last_interaction_at = last_received
            last_interaction_type = "email_received"
        elif last_sent:
            last_interaction_at = last_sent
            last_interaction_type = "email_sent"

        first_interaction_at = None
        if first_received and first_sent:
            first_interaction_at = min(first_received, first_sent)
        else:
            first_interaction_at = first_received or first_sent

        return {
            "sent_count": sent_count,
            "received_count": received_count,
            "recent_received": recent_received,
            "last_interaction_at": last_interaction_at,
            "last_interaction_type": last_interaction_type,
            "first_interaction_at": first_interaction_at,
            "last_sent": last_sent,
            "last_received": last_received,
        }

    def _compute_score(self, stats: dict, now: datetime) -> int:
        """Compute a 0–100 relationship score from interaction stats."""
        sent = stats.get("sent_count", 0)
        received = stats.get("received_count", 0)
        total = sent + received
        recent = stats.get("recent_received", 0)
        last_at = stats.get("last_interaction_at")

        if total == 0:
            return 0

        # Frequency score: log scale, caps at ~50 messages
        import math
        freq_score = min(100, (math.log(total + 1) / math.log(51)) * 100)

        # Recency score: exponential decay
        recency_score = 0
        if last_at:
            days_ago = (now - last_at).total_seconds() / 86400
            if days_ago <= 1:
                recency_score = 100
            elif days_ago <= 7:
                recency_score = 90
            elif days_ago <= 30:
                recency_score = 70
            elif days_ago <= 90:
                recency_score = 45
            elif days_ago <= 180:
                recency_score = 20
            else:
                recency_score = max(0, 10 - (days_ago - 180) / 36)

        # Reciprocity: how balanced is the communication?
        reciprocity_score = 0
        if total > 0:
            if sent > 0 and received > 0:
                ratio = min(sent, received) / max(sent, received)
                reciprocity_score = ratio * 100
            # One-way still gets some credit
            elif sent > 0 or received > 0:
                reciprocity_score = 20

        # Volume: recent activity boost
        volume_score = min(100, recent * 10)

        # Weighted total
        score = (
            freq_score * WEIGHT_FREQUENCY
            + recency_score * WEIGHT_RECENCY
            + reciprocity_score * WEIGHT_RECIPROCITY
            + volume_score * WEIGHT_VOLUME
        )

        return max(0, min(100, round(score)))


# --- Helpers ---

def _get_contact_emails(contact: Contact) -> set[str]:
    """Extract lowercase email addresses from a contact's emails JSONB."""
    emails = set()
    for entry in (contact.emails or []):
        addr = None
        if isinstance(entry, dict):
            addr = entry.get("address") or entry.get("email") or entry.get("value")
        elif isinstance(entry, str):
            addr = entry
        if addr:
            emails.add(addr.lower())
    return emails


def _score_to_segment(score: int) -> str:
    for threshold, segment in SEGMENTS:
        if score >= threshold:
            return segment
    return "Dormant"


def _recency_to_stage(last_interaction_at: Optional[datetime], now: datetime) -> str:
    if not last_interaction_at:
        return "Dormant"
    days = (now - last_interaction_at).total_seconds() / 86400
    for max_days, stage in STAGE_DAYS:
        if days <= max_days:
            return stage
    return "Dormant"
