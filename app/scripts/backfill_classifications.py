"""
One-time backfill: classify existing messages into People / Bulk.

Invoke from the backend container terminal:

    python -m app.scripts.backfill_classifications --dry-run
    python -m app.scripts.backfill_classifications
    python -m app.scripts.backfill_classifications --user-id <UUID>

Default is a REAL RUN — pass --dry-run first to preview. --user-id scopes
to a single user; without it, every user is processed.

This script does NOT auto-run on deploy. Carl runs it manually after
reviewing dry-run output.

============================================================================
LIMITATION — read this before interpreting the dry-run report
============================================================================
Phase 3 deliberately did NOT persist classifier-relevant headers
(List-Unsubscribe, List-ID, Precedence, Auto-Submitted) on existing
messages. That means this backfill cannot apply the header-presence rules
that catch List-Unsubscribe-only newsletters from non-ESP senders.

What the backfill DOES apply:
  - User overrides (skipped — never touched)
  - Reply-history (sender appears in user's sent to_addresses/cc_addresses
    across all their accounts)
  - From-address-only rules from the header gauntlet:
      * mailer-daemon@ / postmaster@ patterns
      * From-domain matches an ESP in KNOWN_ESP_DOMAINS

What the backfill MISSES:
  - Newsletters identifiable only by List-Unsubscribe / List-ID /
    Precedence / Auto-Submitted headers, sent from a non-ESP domain.
    These will remain in People until manually moved.

Manual move + apply_to_domain on a single example covers misses cleanly.
============================================================================
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import time
import uuid
from collections import Counter
from typing import Iterable, Optional

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.account import Account
from app.models.message import Message
from app.models.user import User
from app.services.classification import classify_by_headers


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("backfill")


BATCH_SIZE = 500
PROGRESS_EVERY = 1000


# ---------------------------------------------------------------------------
# Replied-to set
# ---------------------------------------------------------------------------

async def build_replied_to_set(db: AsyncSession, user_id: uuid.UUID) -> set[str]:
    """
    Return a set of lowercased addresses this user has ever sent to (across
    every one of their accounts). Reads to_addresses + cc_addresses; skips
    bcc per the Phase 2 spec. Skips archived sent messages.
    """
    user_accounts = select(Account.id).where(Account.user_id == user_id)
    q = (
        select(Message.to_addresses, Message.cc_addresses)
        .where(
            Message.account_id.in_(user_accounts),
            Message.is_sent.is_(True),
            Message.is_archived.is_(False),
        )
    )
    result = await db.execute(q)
    addrs: set[str] = set()
    for to_list, cc_list in result.all():
        for entries in (to_list or [], cc_list or []):
            for entry in entries:
                addr = (entry or {}).get("address") if isinstance(entry, dict) else None
                if addr:
                    a = addr.strip().lower()
                    if a:
                        addrs.add(a)
    return addrs


# ---------------------------------------------------------------------------
# Per-message verdict
# ---------------------------------------------------------------------------

def verdict_for_message(
    msg: Message,
    replied_to: set[str],
) -> Optional[tuple[str, str]]:
    """
    Return (category, category_source) the row SHOULD have, or None if no
    write is needed.

    Returns None when:
      - Source is already 'override' (user has spoken — never touch)
      - The new verdict would be ('people', 'default'), which is the
        schema default — re-asserting it is a no-op write that pointlessly
        bumps updated_at, so we skip it.
    """
    if msg.category_source == "override":
        return None

    addr_lower = (msg.from_address or "").strip().lower()

    # 1. Reply history (the most valuable signal — it catches actual humans)
    if addr_lower and addr_lower in replied_to:
        new = ("people", "history")
        return new if (msg.category, msg.category_source) != new else None

    # 2. Header / ESP rules. We only have from_address available — old
    # messages don't have classifier-relevant headers persisted (see
    # module docstring). classify_by_headers still works because the
    # mailer-daemon / postmaster / ESP-domain rules read from_address only.
    header_verdict = classify_by_headers(
        from_address=msg.from_address or "",
        headers={},  # no persisted classifier headers
        content_type=None,
    )
    if header_verdict is not None:
        return (
            header_verdict
            if (msg.category, msg.category_source) != header_verdict
            else None
        )

    # 3. Default — already the schema default; skip the write.
    return None


# ---------------------------------------------------------------------------
# Main per-user loop
# ---------------------------------------------------------------------------

async def backfill_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    dry_run: bool,
) -> dict:
    """Backfill one user. Returns a summary dict."""
    started = time.monotonic()
    logger.info("User %s — building replied-to set…", user_id)
    replied_to = await build_replied_to_set(db, user_id)
    logger.info("User %s — replied-to set: %d addresses", user_id, len(replied_to))

    # Keyset pagination over non-sent, non-archived messages on this user's
    # accounts. Earlier versions used a streaming cursor (yield_per/stream),
    # but commit-per-batch terminates the transaction and kills the cursor —
    # so we materialize each 500-row page, commit, then page forward by
    # `id > last_seen_id`. Using id (UUID) as the keyset key works because
    # it's the PK and totally ordered; concurrent inserts of new rows at
    # higher ids don't disrupt the scan, and we never re-visit a row.
    user_accounts_subq = select(Account.id).where(Account.user_id == user_id).subquery()

    counts = Counter()
    sample = {"history": [], "headers": []}
    processed = 0
    last_seen_id: Optional[uuid.UUID] = None

    while True:
        page_q = (
            select(Message)
            .where(
                Message.account_id.in_(select(user_accounts_subq.c.id)),
                Message.is_sent.is_(False),
                Message.is_archived.is_(False),
            )
            .order_by(Message.id)
            .limit(BATCH_SIZE)
        )
        if last_seen_id is not None:
            page_q = page_q.where(Message.id > last_seen_id)

        page = (await db.execute(page_q)).scalars().all()
        if not page:
            break

        pending_updates: list[tuple[uuid.UUID, str, str]] = []
        for msg in page:
            processed += 1
            verdict = verdict_for_message(msg, replied_to)

            if verdict is None:
                if msg.category_source == "override":
                    counts["skip_override"] += 1
                else:
                    counts["skip_default_unchanged"] += 1
                continue

            new_cat, new_src = verdict
            counts[f"reclassified_{new_src}"] += 1
            counts[f"target_{new_cat}"] += 1
            if len(sample[new_src]) < 5:
                sample[new_src].append({
                    "id": str(msg.id),
                    "from": msg.from_address,
                    "subject": msg.subject,
                    "old": (msg.category, msg.category_source),
                    "new": (new_cat, new_src),
                })

            pending_updates.append((msg.id, new_cat, new_src))

            if processed % PROGRESS_EVERY == 0:
                logger.info(
                    "User %s — processed %d, history=%d headers=%d, override=%d unchanged=%d",
                    user_id, processed,
                    counts["reclassified_history"],
                    counts["reclassified_headers"],
                    counts["skip_override"],
                    counts["skip_default_unchanged"],
                )

        # Flush this batch's writes (or commit nothing on dry-run).
        if not dry_run and pending_updates:
            await _flush_batch(db, pending_updates)
        elif dry_run:
            # No writes, but advance any in-session state by rolling back
            # so successive pages don't accumulate identity-map noise.
            await db.rollback()

        # Advance the cursor. Use the page's max id, not the last
        # `pending_updates` id — a page can contain rows that produced no
        # update, and we still need to skip past them next iteration.
        last_seen_id = page[-1].id

        # Short page → done.
        if len(page) < BATCH_SIZE:
            break

    elapsed = time.monotonic() - started

    # Summary
    logger.info(
        "User %s backfill %s.\n"
        "  Messages processed: %d\n"
        "  Reclassified: %d\n"
        "    people / history: %d\n"
        "    bulk   / headers: %d\n"
        "  Skipped (already default — no-op): %d\n"
        "  Skipped (override): %d\n"
        "  Time: %.1fs",
        user_id, "DRY RUN" if dry_run else "complete",
        processed,
        counts["reclassified_history"] + counts["reclassified_headers"],
        counts["reclassified_history"],
        counts["reclassified_headers"],
        counts["skip_default_unchanged"],
        counts["skip_override"],
        elapsed,
    )

    if dry_run:
        for src in ("history", "headers"):
            if sample[src]:
                logger.info("Sample of would-flip messages (%s):", src)
                for s in sample[src]:
                    logger.info(
                        "  %s  from=%s  subject=%r  %s → %s",
                        s["id"], s["from"], (s["subject"] or "")[:60],
                        s["old"], s["new"],
                    )

    return {
        "user_id": str(user_id),
        "processed": processed,
        "reclassified_history": counts["reclassified_history"],
        "reclassified_headers": counts["reclassified_headers"],
        "skip_override": counts["skip_override"],
        "skip_default_unchanged": counts["skip_default_unchanged"],
        "elapsed_seconds": elapsed,
    }


async def _flush_batch(db: AsyncSession, updates: list[tuple[uuid.UUID, str, str]]):
    """
    Apply a batch of per-row updates. Group by (category, category_source)
    so we issue at most a few UPDATEs per batch instead of one per row.
    Commit after the batch.
    """
    by_verdict: dict[tuple[str, str], list[uuid.UUID]] = {}
    for mid, cat, src in updates:
        by_verdict.setdefault((cat, src), []).append(mid)

    for (cat, src), ids in by_verdict.items():
        await db.execute(
            update(Message)
            .where(Message.id.in_(ids))
            .values(category=cat, category_source=src)
            .execution_options(synchronize_session=False)
        )
    await db.commit()


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

async def run(*, dry_run: bool, user_id: Optional[uuid.UUID]) -> None:
    logger.warning(
        "Backfill mode: %s",
        "DRY RUN — no writes will be made" if dry_run else "REAL RUN — writes will be committed",
    )
    logger.warning(
        "Note: legacy messages do not have classifier headers persisted. "
        "List-Unsubscribe-only newsletters from non-ESP domains will remain "
        "in People until manually moved. See module docstring."
    )

    async with async_session() as db:
        if user_id is not None:
            user_ids: list[uuid.UUID] = [user_id]
        else:
            user_ids = list(
                (await db.execute(select(User.id))).scalars().all()
            )
        logger.info("Backfilling %d user(s)", len(user_ids))

        global_summary = []
        for uid in user_ids:
            try:
                summary = await backfill_user(db, uid, dry_run=dry_run)
                global_summary.append(summary)
            except Exception as e:
                logger.exception("User %s — failed: %s", uid, e)

        # Global summary
        total_processed = sum(s["processed"] for s in global_summary)
        total_history = sum(s["reclassified_history"] for s in global_summary)
        total_headers = sum(s["reclassified_headers"] for s in global_summary)
        total_override = sum(s["skip_override"] for s in global_summary)
        total_default = sum(s["skip_default_unchanged"] for s in global_summary)
        total_time = sum(s["elapsed_seconds"] for s in global_summary)

        logger.info(
            "==============================\n"
            "GLOBAL SUMMARY (%d user%s, %s):\n"
            "  Processed: %d\n"
            "  Reclassified people/history: %d\n"
            "  Reclassified bulk/headers:   %d\n"
            "  Skipped override:            %d\n"
            "  Skipped default-unchanged:   %d\n"
            "  Total time: %.1fs",
            len(global_summary), "" if len(global_summary) == 1 else "s",
            "DRY RUN" if dry_run else "REAL RUN",
            total_processed, total_history, total_headers,
            total_override, total_default, total_time,
        )


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill People/Bulk classifications for existing messages.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing. Default is a real run.",
    )
    p.add_argument(
        "--user-id",
        type=str,
        default=None,
        help="Restrict to a single user UUID. Default: all users.",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = _parse_args(argv)
    user_uuid = uuid.UUID(args.user_id) if args.user_id else None
    asyncio.run(run(dry_run=args.dry_run, user_id=user_uuid))


if __name__ == "__main__":
    main()
