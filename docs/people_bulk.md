# People / Bulk classification

DevEmail buckets every received message into one of two categories — **People**
(humans you correspond with) or **Bulk** (newsletters, transactional mail,
notifications, calendar invites, DSNs). The Inbox view filters on this with
three pills above the list: **All · People · Bulk**. Sent mail is excluded
from the People/Bulk views and lives in the Sent folder as before.

## How a message gets classified

At sync time, every newly-arriving message runs through a four-step gauntlet.
Stop at the first match:

1. **Override.** `sender_classifications` row scoped to this account.
   Address-level rule wins; falls back to domain-level if no address rule.
   `category_source = 'override'`.
2. **Reply history.** Any sent message — across ANY of your accounts — whose
   `to_addresses` or `cc_addresses` contains this sender. Skips `bcc`.
   `category_source = 'history'`.
3. **Header rules → Bulk.** Any one of:
   - `List-Unsubscribe` header present
   - `List-ID` header present
   - `Precedence: bulk` or `Precedence: list`
   - `Auto-Submitted` header present and not `no`
   - `Content-Type: text/calendar` (calendar invites)
   - `Content-Type: multipart/report` (DSNs / bounces)
   - `From:` localpart is `mailer-daemon` or `postmaster`
   - From or `Return-Path` domain on the ESP allow-list
     (`mailchimp.com`, `sendgrid.com`, `mailgun.org`, `amazonses.com`,
     `klaviyo.com`, `hubspot.com`, `substack.com`, `beehiiv.com`,
     `marketo.com`, `pardot.com`, `braze.com`, `brevo.com`, … — see
     `KNOWN_ESP_DOMAINS` in `app/services/classification.py`).
   `category_source = 'headers'`.
4. **Default → People.** `category_source = 'default'`.

The full ESP list, ordering, and per-rule behavior live in
[`app/services/classification.py`](../app/services/classification.py).

## Manual moves

Right-click any message → **Move to People** or **Move to Bulk**. The modal
offers two opt-in checkboxes:

- **Apply to entire @domain.com** — creates a domain-level rule instead of
  an address-level one. Future mail from any address in this domain
  classifies per the rule.
- **Apply to existing messages from this sender** — bulk-updates older
  messages from the same sender (or domain) to match the new category.

A manual move ALWAYS upserts a `sender_classifications` row, even with both
checkboxes unchecked. Otherwise the next message from that sender would
reclassify back to default and the user's intent would be forgotten.
The two checkboxes only control:
- the *scope* of the rule (address vs. domain), and
- whether OLD messages get swept.

After a sweep the toast reports the count: e.g. "Moved 462 messages to Bulk".

## Cross-account scope

- **Reply history** is user-scoped. Replying from your work account counts
  as a People signal when that same person mails your personal account.
  This catches misdirected sends.
- **Overrides** are account-scoped. Work and personal can disagree about
  the same sender. Deliberate — different contexts, different mail.

## Known limitation: bulk reclassification

Classifier-relevant headers (`List-Unsubscribe`, `List-ID`, `Precedence`,
`Auto-Submitted`) are **not** persisted on the `messages` table. They're
read from the live IMAP/Gmail response at sync time, used to classify,
and discarded.

Consequence: the one-time backfill script
([`app/scripts/backfill_classifications.py`](../app/scripts/backfill_classifications.py))
can only apply the from-address-only subset of the header gauntlet to
existing mail. Newsletters identifiable only by `List-Unsubscribe` from a
non-ESP domain stay in People until manually moved. Manual move +
**Apply to domain** + **Apply to existing** covers the misses cleanly.

If bulk reclassification ever becomes a regular need, the cheap fix is to
add a `Message.classification_headers JSONB` column at sync time. Deferred
until justified by demand.

## Operations

- **Backfill.** Run once after deploying classifier changes:
  ```
  python -m app.scripts.backfill_classifications --dry-run
  python -m app.scripts.backfill_classifications
  ```
  Idempotent. The script skips override'd rows and skips writes that would
  re-assert the schema default `(people, default)`.
- **Override scope check.**
  ```sql
  SELECT * FROM sender_classifications
  WHERE sender_address != lower(sender_address);
  ```
  Should return zero rows. The manual-move handler lowercases at write.
  Phase 8 also lowercased every existing `messages.from_address` and the
  JSONB recipient lists.

## Out of scope (for now)

- A Settings UI to view/edit `sender_classifications` directly. The CRUD
  endpoints exist (`/api/sender-classifications`); the UI is a future
  pure-frontend addition.
- ML-based scoring. Rules-only for v1.
- Per-message "why was this classified as X?" debug view.
- Notification preferences per category.
