# Phase 2 Recon — Classifier Prep

Recon-only report. No code changes. Findings drive the Phase 2 design choice
between query-time JSONB containment vs. a denormalized `user_reply_contacts`
cache for the reply-history check.

---

## 1. Address normalization at ingest

**TL;DR — addresses are NOT lowercased anywhere on write. Trimming happens but
case is preserved as received.** This is a real correctness problem for the
Phase 2 reply-history query and worth fixing in a separate cleanup pass.

### Write paths

There are five paths that insert into `messages` or write address fields:

#### 1a. Gmail API sync — primary inbound path

`app/services/gmail_sync.py:707-735` — `_parse_email_address` and
`_parse_address_list`.

- Input: raw `From:` / `To:` / `Cc:` / `Bcc:` header strings from Gmail API.
- `.strip()` on the name part (line 713) and `.strip()` on the address part
  (line 714, 717, 729).
- **No `.lower()` anywhere.** `Foo@Example.COM` is stored as `Foo@Example.COM`.
- Used at `gmail_sync.py:422` (`from_address`), `:476–478` (to/cc/bcc).

#### 1b. IMAP sync (Stalwart-style)

`app/services/imap_sync.py:61-76` — `parse_address` and `parse_address_list`.

- Wraps stdlib `email.utils.parseaddr`. Returns `{name, address}` dict.
- `.strip()` on each comma-split part (line 73).
- **No `.lower()`.** `parseaddr` does not lowercase by default.
- Used at `imap_sync.py:273-275` then written at `:304-308`.

#### 1c. Stalwart raw-email sync

`app/services/stalwart_sync.py:475-505` — `_parse_email_header_address` and
`_parse_header_address_list`.

- Decodes RFC 2047 (`_decode_header`) then `.strip()`s each part.
- **No `.lower()`.**
- Used at `stalwart_sync.py:256, 308-310`.

#### 1d. Compose / send (outbound)

`app/services/email_send.py:369-390` — `EmailSendService.send_message` writes
the persisted sent-folder copy.

- `from_address=self.account.email_address` (line 373) — uses whatever case
  the user entered when adding the account.
- `to_addresses=to`, `cc_addresses=cc`, `bcc_addresses=bcc` — these dicts
  arrive from `app/routers/messages.py:802-807` via
  `[a.model_dump() for a in request.to_addresses]`. The Pydantic schema
  (`app/schemas/message.py:8-10`) is a plain `EmailAddress(address: str,
  name: Optional[str])` with **no validator that lowercases**.
- **No `.lower()`.** Whatever case the compose UI sent is what's stored.

#### 1e. Draft save (compose with `is_draft=True`)

`app/routers/messages.py:732-766` — same Pydantic-driven dump, same lack of
normalization.

- `from_address=account.email_address` (line 758)
- `to_addresses=[a.model_dump() for a in request.to_addresses]` (line 760), etc.
- **No `.lower()`.**

### Inconsistencies

- All five paths agree on **structure**: `from_address` is a flat string,
  `to_addresses`/`cc_addresses`/`bcc_addresses` are JSONB lists of `{name,
  address}` objects.
- All five agree on **trimming**: leading/trailing whitespace stripped from
  both the address and the display name.
- All five agree on **what they don't do**: nobody lowercases.
- Existing reads compensate ad-hoc:
  - `app/services/contact_scoring.py:178, 216` does
    `func.lower(Message.from_address).in_(contact_emails)` — query-time lower.
  - `app/services/contact_scoring.py:201` does
    `Message.to_addresses.cast(text("TEXT")).ilike(f"%{email_addr}%")` —
    case-insensitive substring match (note: this is a full table scan
    against JSONB cast to TEXT; it's correct but slow).

### Recommendation (deferred — not for Phase 2)

A separate cleanup migration that:
1. Lowercases the `address` field in every JSONB list element of
   `to_addresses`, `cc_addresses`, `bcc_addresses` for all rows.
2. Lowercases `from_address` for all rows.
3. Updates all five write paths to lowercase before insert.

Worth doing because `contact_scoring.py` already pays the cost at query time
and JSONB `@>` containment in Phase 2 will need lowercasing on both sides
anyway. Out of scope for the People/Bulk PR — flag for a follow-up.

**For Phase 2:** lowercase on both sides of every comparison. Don't rely on
ingest normalization that doesn't exist. The classifier's
`_check_reply_history` and `_check_override` must lowercase
`sender_address` arg before comparing, and use `lower()` on the JSONB-
extracted `address` field on the DB side.

---

## 2. Existing indexes touching address / sent / account columns

Searched both `app/models/` and `alembic/versions/`.

### On `messages`

| Column / shape                          | Index? | Source |
|-----------------------------------------|--------|--------|
| `account_id`                            | implicit B-tree (FK) | `messages.account_id` is FK; no explicit index but Postgres FK doesn't auto-index — **no index** |
| `(account_id, remote_id)`               | unique constraint (B-tree) | `messages.py:11-13` `uq_messages_account_remote` |
| `remote_thread_id`                      | B-tree | `messages.py:20` `index=True` |
| `tracking_token`                        | unique B-tree | `messages.py:44` |
| `category` (added Phase 1)              | B-tree | migration `008_add_classification.py:41` |
| `from_address`                          | **none** |  |
| `to_addresses` (JSONB)                  | **none** |  |
| `cc_addresses` (JSONB)                  | **none** |  |
| `bcc_addresses` (JSONB)                 | **none** |  |
| `is_sent`                               | **none** |  |

### GIN indexes

**There are zero GIN indexes anywhere in the schema.** Verified by
`grep -rn "GIN\|gin_" app/models alembic/versions` returning nothing.

### Implication for Phase 2

A reply-history query like

```sql
SELECT 1
FROM messages
JOIN accounts ON messages.account_id = accounts.id
WHERE accounts.user_id = :user_id
  AND messages.is_sent = true
  AND messages.to_addresses @> :sender_addr_jsonb
LIMIT 1
```

will today be a **sequential scan** on `messages` filtered by `is_sent`. No
index helps the JSONB lookup. Performance is bounded by sent-message volume
per user.

If we go the JSONB-containment route, Phase 2 should also add:

```sql
CREATE INDEX ix_messages_is_sent_account ON messages (account_id, is_sent)
  WHERE is_sent = true;
CREATE INDEX ix_messages_to_addresses_gin ON messages USING gin (to_addresses);
CREATE INDEX ix_messages_cc_addresses_gin ON messages USING gin (cc_addresses);
```

The partial index on `is_sent = true` is small (sent volume is much smaller
than received). The GIN indexes are larger but they're the only way to make
JSONB containment fast enough for sync-hot-path use.

---

## 3. Sent-message volume per user

**Cannot run this query — I don't have access to the production database from
this environment.** Need you to run it manually and paste the output, or
authorize me a read-only psql.

Suggested SQL (drop into Railway / your DB client):

```sql
-- Per-user sent-message counts
WITH per_user AS (
  SELECT a.user_id, COUNT(*) AS sent_count
  FROM messages m
  JOIN accounts a ON a.id = m.account_id
  WHERE m.is_sent = true
  GROUP BY a.user_id
)
SELECT
  COUNT(*)                                      AS user_count,
  COALESCE(SUM(sent_count), 0)                  AS total_sent,
  COALESCE(MAX(sent_count), 0)                  AS max_per_user,
  COALESCE(
    PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY sent_count), 0
  )                                             AS median_per_user,
  COALESCE(
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY sent_count), 0
  )                                             AS p95_per_user
FROM per_user;
```

### How the answer drives the design

- **If max ≤ ~5,000 and p95 ≤ ~1,000**: query-time JSONB containment is fine.
  The classifier's reply-history check stays a single SQL query per incoming
  message. With the GIN index from §2, this is sub-millisecond per lookup.
- **If max ≥ ~50,000 or p95 ≥ ~10,000**: build a denormalized
  `user_reply_contacts(user_id, recipient_address)` table. Populated by a
  trigger on `messages` insert (or a write-through helper in the send path)
  + a one-shot backfill. Reply-history check becomes a simple primary-key
  hit on `(user_id, lower(sender_address))` — cheap regardless of volume.
  Cost: extra table, extra write per send, more migration surface.
- **In between**: lean toward containment for now (simpler), revisit if the
  classifier shows up in slow-query logs.

You're a single user of this app right now (per project memory), so the
realistic answer is "containment is fine for v1, build the cache only when
volume justifies it." But I'd still like the actual number before I commit.

---

## 4. Existing helpers for extracting addresses from JSONB lists

**None.** Searched for `extract_addresses`, `jsonb_array_elements`, `@>`,
`->>'address'`, and any obvious Python helper that walks a list-of-dicts
column.

The only place that reads addresses out of JSONB is
`app/services/contact_scoring.py:201`:

```python
Message.to_addresses.cast(text("TEXT")).ilike(f"%{email_addr}%")
```

— a TEXT cast + ILIKE, which is functional but does a sequential scan and
is brittle (could match the address inside a display name). Not reusable for
the classifier; would amplify the slow-query problem at sync rate.

**For Phase 2:** I'll need to write a small SQLAlchemy helper that emits
`to_addresses @> :jsonb` (with `:jsonb` built from the lowercased sender
address as `'[{"address": <addr>}]'::jsonb`), or — if we want the partial
index to bite — `EXISTS (SELECT 1 FROM jsonb_array_elements(to_addresses)
elt WHERE lower(elt->>'address') = :addr)`. The right form depends on
whether ingest is normalized (§1) or not.

---

## 5. Sync hot path — where new incoming messages get persisted

### Persistence site

**`app/services/gmail_sync.py:411-485`** — `GmailSyncService._store_message`.
This is the funnel for every newly synced Gmail message. Three callers:

- `sync_messages` (line 176) — full / first-run sync
- `_sync_via_history` (line 330) — incremental history.list sync (the hot
  path for an established account)
- `routers/messages.py:491, 548, 865` — manual force-sync endpoints

The classifier hooks in at `_store_message` immediately before the
`Message(...)` constructor at `gmail_sync.py:464`. Pass:
- `db_session=self.db`
- `user_id=self._user_id` (snapshot from Phase 1's `gmail_sync` refactor —
  good news, this is already a plain attribute, no expired-ORM risk)
- `account_id=self._account_id`
- `sender_address=from_address` (the parsed address string at line 422)
- `headers=headers` (the dict built at line 416-419 — see retention note
  below)
- `content_type=headers.get("content-type")`

Then assign `message.category` and `message.category_source` to the
`Message(...)` constructor kwargs.

The IMAP and Stalwart paths (`app/services/imap_sync.py:296` and
`app/services/stalwart_sync.py:300`) need the same hook. Per Phase 3 prompt
this is in scope.

### Header retention

Phase 3 of the spec calls out that we need `List-Unsubscribe`, `List-ID`,
`Precedence`, `Auto-Submitted` retained.

**Today:** `app/services/gmail_sync.py:416-419` builds a `headers` dict by
iterating `payload.get("headers", [])` from the Gmail API response and
lowercasing the names. That dict is **not persisted** — it lives only in
the local stack frame of `_store_message` and is discarded after the
Message is built. Only `from_address`, `subject`, `message_id_header`,
`in_reply_to`, `references`, `received_at` survive.

There's a partial workaround: `list-unsubscribe` is read at line 522 and
written into `unsubscribe_links` table via `_store_unsubscribe`. So
unsubscribe info is preserved, but as a separate row, and the other three
classifier-relevant headers are dropped.

**For Phase 3:** classification only needs the headers at the moment of
classification — we have them in the local `headers` dict already. We
don't need to persist them just to classify. But if we want
*re-classification* later (e.g. user changes their classifier rules and
wants to re-bucket existing mail), we'd need to either:
1. Add a `Message.classification_headers JSONB` column storing just the
   four classifier-relevant headers, or
2. Re-fetch from Gmail on demand (slow, rate-limited).

I'd push for option 1 — small JSONB column, populated at sync time. Lets
us re-run the classifier without re-syncing. Cheap.

For the IMAP and Stalwart paths, the raw `email.message.Message` object is
available at the persistence site so the same headers can be extracted
directly with `msg.get("List-Unsubscribe")` etc.

### Throughput

I don't have production logs in this environment. Estimating from config:

- `app/main.py:25` — `SYNC_INTERVAL_SECONDS = 300` (5 minutes)
- `app/services/gmail_sync.py:145` — `max_results: int = 500` per first-run
  sync
- Incremental sync (`_sync_via_history`) processes only `messagesAdded` since
  the last `historyId` — typically single digits per cycle for a single
  user, possibly hundreds during a backfill or after a long offline period.

**Realistic peak:** the bursty case is a first-run sync of a fresh account
or a long-offline reconnect. That's ~500 messages serially through
`_store_message` over a few minutes — call it ~3-10 messages/sec
sustained, with HTTP latency to Gmail dominating. The classifier needs to
add no more than a few milliseconds per call to be invisible. Steady-state
peak is under 1 message/sec.

**Implication:** even a slow query-time JSONB containment that takes ~5ms
is fine here. The classifier will not be a bottleneck unless it does
something pathological (per-message N+1 over thousands of override rows
or full table scans without an index). Defensive caching of the override
table per `_store_message` batch would be a nice-to-have but is unlikely
to matter at v1 scale.

---

## Summary — what Phase 2 needs to handle

1. **Lowercase on both sides at query time.** Ingest does not normalize.
   Don't add normalization to ingest in this PR — note it as follow-up
   work.
2. **Use JSONB containment with GIN.** Add the GIN indexes (and the partial
   `is_sent` index) as part of the Phase 2 migration. Don't build a
   denormalized cache yet — wait for the §3 numbers.
3. **No existing JSONB-extract helper.** Write one for Phase 2 (small,
   probably in `app/classification/jsonb_addresses.py` or inline in the
   classifier).
4. **Hook in at `_store_message`.** The Gmail path is clean (already has a
   `headers` dict). IMAP and Stalwart paths need parallel hooks.
5. **Don't persist classifier headers in this PR.** Use them at sync time
   and discard. If re-classification becomes a feature, add a JSONB column
   then.

## Open questions (need your answer before Phase 2 starts)

1. **Run the query in §3** and paste the result. Without it I'm
   guessing at scale.
2. **GIN index decision.** OK to add `to_addresses`/`cc_addresses` GIN
   indexes + partial `(account_id, is_sent) WHERE is_sent = true` in the
   Phase 2 migration?
3. **Address-lowercasing cleanup pass.** Want me to do this in a separate
   PR after Phase 2 ships, or fold it in?
4. **Classifier header persistence.** Confirm we can defer (option 1, no
   `classification_headers` column right now).
