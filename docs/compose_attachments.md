# Compose attachments

DevEmail's compose flow supports outbound file attachments end-to-end:
files chosen in the compose modal are persisted to disk, attached to
draft messages, sent via the appropriate provider (Gmail API or SMTP),
and survive transport failures as drafts.

This doc covers the architecture, the storage model, the HTTP surface,
configuration, production setup, and known limitations.

---

## 1. Architecture overview

The `POST /api/messages/compose` endpoint accepts both JSON and
multipart/form-data based on `Content-Type`. The handler dispatches
internally:

- **`application/json`** — backward-compatible body shape
  (`ComposeRequest`). No attachments. The original send + draft flow.
- **`multipart/form-data`** — a single `payload` form field carrying
  the same `ComposeRequest` JSON, plus zero or more `attachments` file
  parts. Same field shape as the JSON path; the frontend just builds
  `FormData` instead of a JSON body.

Regardless of intent, the handler **always pre-creates the message as a
draft first**. Attachment files + DB rows are persisted while the row is
still `is_draft=true`. Only after that initial transaction commits do
we attempt the actual send (if `is_draft=false` was requested).

### The send-from-draft flip

When `is_draft=false`:

1. Read attachment bytes off disk via the storage layer.
2. Call `EmailSendService.send_from_draft(draft_message, ...)`.
3. The service builds the MIME message, calls the provider transport
   (`_send_gmail` or `_send_smtp`), and on **success** updates the
   existing draft row in place: `is_draft=False`, `is_sent=True`,
   `sent_at`, `received_at`, `remote_id`, `body_html` (rewritten to
   include the open-tracking pixel), `tracking_token`,
   `has_attachments`. The Attachment rows already point at this same
   message id, so they travel into the Sent folder without any FK
   gymnastics.
4. On **failure**, an HTTPException 502 is raised with detail "*The
   draft has been saved — open it from the Drafts folder to retry.*"
   The draft row, attachment rows, and on-disk files all survive
   intact (they were committed in step 1, untouched by the failed
   send attempt).

### Sending a restored draft

When the user reopens a draft from the Drafts folder, the modal:

1. Hydrates body / recipients / subject from the draft.
2. Captures `draftId` so subsequent file picks upload directly to
   `POST /messages/{id}/attachments`.
3. On Send, calls `POST /api/messages/compose` with
   `existing_message_id` set and no file parts. The backend validates
   the message is a draft owned by the user, refreshes its body /
   recipients, then calls `send_from_draft`.

The "edit a draft" entry point lives on `MessageBubble` — drafts in the
inbox view show an **Edit** button next to the existing Draft badge.

---

## 2. Storage layer (`app/services/attachment_storage.py`)

Outbound attachment bytes are persisted to disk. The DB row owns
everything else.

### Filename strategy

- **On disk:** UUID with no extension. The original filename is never
  used as a path component, so MIME-type spoofing via filename
  extension is impossible, and there are no filename-collision bugs.
- **In the DB:** `attachments.filename` holds the user-facing filename
  (sanitized). This is what gets shown in UI and what feeds the MIME
  `Content-Disposition: attachment; filename=...` header.

### `storage_path` is relative

`storage_path` in the DB is the UUID alone — relative to
`ATTACHMENT_STORAGE_DIR`. The storage layer reconstructs the absolute
path on every read/delete. The storage directory can be relocated
without rewriting any DB rows.

### Filename sanitization

`_sanitize_filename` runs on every save:

- Strips path components (handles both `/` and `\`)
- Strips control characters (0x00–0x1F) and null bytes
- Strips leading dots
- Defaults blank/None to `"attachment"`
- Truncates to 255 chars while preserving the file extension

The sanitized result is what's stored in `attachments.filename` AND
what's emitted in the MIME header.

### Path-traversal defense (double-layered)

1. **At write time:** `_sanitize_filename` strips path separators, so
   the filename can never become a malicious `storage_path`.
2. **At read/delete time:** `_absolute(storage_path)` rebuilds the
   absolute path AND verifies (via `Path.resolve()` + `relative_to()`)
   that the result is still inside `ATTACHMENT_STORAGE_DIR`. If a
   future bug ever lets a `..` reach this layer, the read raises
   `ValueError` and the delete logs and bails — no filesystem access
   outside the storage root.

### Best-effort delete

`delete(storage_path)` is best-effort:

- Missing file → no error. The DB row is the authority; if the file is
  already gone, the desired post-state is satisfied.
- OS error (permissions, etc.) → logged, **not raised**. The caller's
  transaction has already (or will) commit the DB delete; an orphaned
  file is recoverable, lost data isn't.
- Path-traversal attempt on the input (shouldn't happen, defense in
  depth) → logged, returns silently without touching the filesystem.

**Cleanup ordering rule:** commit the DB delete first, **then** unlink
the file. Reversing this order risks unlinking a file that a rolled-
back transaction needed. This rule applies to:

- `DELETE /messages/{id}/attachments/{att_id}` (the manual delete path)
- ON DELETE CASCADE when a Message is deleted (the cascade unlinks the
  rows; orphan files cleaned up by a future periodic sweep — not yet
  implemented)
- The partial-write rollback in compose / per-draft upload (when a
  cap-rejection mid-batch unwinds files written so far)

---

## 3. Environment variables

| Variable                  | Default                          | Purpose                                                             |
| ------------------------- | -------------------------------- | ------------------------------------------------------------------- |
| `ATTACHMENT_MAX_BYTES`    | `26214400` (25 × 1024 × 1024)    | Server-authoritative cap. Frontend fetches via `/messages/config/attachments` and gates UI; backend enforces on every upload. |
| `ATTACHMENT_STORAGE_DIR`  | `/var/devemail/attachments`      | Absolute path where attachment files are written. Created on first write (`mkdir -p`). |

Both are plain pydantic-settings fields on `app.config.Settings`. Set
via `.env`, container env vars, or the deploy platform's secret
mechanism — same pattern as every other DevEmail setting.

---

## 4. Production setup (Coolify)

The **storage directory must be a persistent volume**. Without it,
every redeploy wipes draft attachments. The DB rows survive (they
point at orphan storage_path UUIDs that no longer have files behind
them), but every `GET .../download` call returns 404 from that point
forward.

### Step-by-step in the Coolify UI

1. Open the DevEmail app in Coolify.
2. **Storages** tab → **Add storage**.
3. Choose **Persistent Volume**.
4. Name: `devemail-attachments` (or whatever).
5. Mount path: `/var/devemail/attachments` (or whatever you set
   `ATTACHMENT_STORAGE_DIR` to in this app's env).
6. Save and redeploy.

After the redeploy, verify the volume is mounted:

```bash
# In the backend container shell:
df -h /var/devemail/attachments        # should show the volume, not /
ls -la /var/devemail/attachments       # writable by the backend uid
```

If the volume mount is missing, the storage layer will silently
`mkdir -p` the path inside the container's writable layer and writes
will succeed — but they'll vanish on the next deploy. The first
symptom users hit is an attachment download 404 some time after a
deploy. Verify the mount before considering Phase 9 ready in
production.

### Optional: override the cap

If the user has an SMTP/IMAP setup with a different size limit (or you
want headroom for future Gmail bumps), set:

```
ATTACHMENT_MAX_BYTES=52428800   # 50 MiB
```

Restart the backend after changing. The frontend re-fetches the cap on
every modal open, so no client deploy is needed.

---

## 5. HTTP API surface

| Method | Path                                                                  | Purpose                                                            |
| ------ | --------------------------------------------------------------------- | ------------------------------------------------------------------ |
| GET    | `/api/messages/config/attachments`                                    | Server cap. `{ "max_bytes": int }`.                               |
| POST   | `/api/messages/compose`                                               | JSON or multipart. Draft or send. See below.                       |
| GET    | `/api/messages/{id}/attachments`                                      | List attachments on a message (metadata only).                     |
| POST   | `/api/messages/{id}/attachments`                                      | Multipart upload of additional files to a draft.                   |
| DELETE | `/api/messages/{id}/attachments/{att_id}`                             | Remove one attachment (row + on-disk file).                        |
| GET    | `/api/messages/{id}/attachments/{att_id}/download`                    | Download attachment bytes.                                         |
| GET    | `/api/messages/{id}/inline/{content_id}`                              | Inline image bytes (used by HTML body cid: rewriting).             |

All endpoints are scoped to the authenticated user's accounts via the
existing `_get_message_or_404` helper. Cross-user access returns 404
(no existence leak), matching the rest of `/messages/{id}/*`.

### `GET /api/messages/config/attachments`

```json
200 OK
{ "max_bytes": 26214400 }
```

### `POST /api/messages/compose` — JSON

Body: `ComposeRequest`. No attachments. Same shape as before Phase 9.

```json
{
  "account_id": "uuid",
  "to_addresses": [{"address": "x@y.com", "name": "X"}],
  "cc_addresses": [],
  "bcc_addresses": [],
  "subject": "hi",
  "body_html": "<p>...</p>",
  "body_text": "...",
  "in_reply_to_message_id": null,
  "signature_id": null,
  "read_receipt_requested": false,
  "is_draft": false,
  "existing_message_id": null
}
```

Response on draft save:

```json
201 Created
{ "message_id": "uuid", "thread_id": "uuid", "status": "draft" }
```

Response on send success:

```json
201 Created
{ "message_id": "uuid", "thread_id": "uuid", "status": "sent" }
```

### `POST /api/messages/compose` — multipart

```
Content-Type: multipart/form-data; boundary=...

--...
Content-Disposition: form-data; name="payload"
Content-Type: application/json

{"account_id":"uuid","to_addresses":[...],"subject":"hi",...,"is_draft":false}
--...
Content-Disposition: form-data; name="attachments"; filename="report.pdf"
Content-Type: application/pdf

<bytes>
--...
Content-Disposition: form-data; name="attachments"; filename="image.png"
Content-Type: image/png

<bytes>
--...--
```

Same response shape as the JSON path.

### `POST /api/messages/compose` — send-from-existing-draft

When `existing_message_id` is set in the JSON body, the endpoint sends
the draft in place instead of creating a new message. **Multipart file
parts are forbidden in this mode** — uploads must go through
`POST /messages/{id}/attachments` first.

```json
{
  "account_id": "uuid",
  "to_addresses": [...],
  "subject": "hi",
  ...
  "is_draft": false,
  "existing_message_id": "draft-uuid"
}
```

Errors specific to this branch:
- `400` — `is_draft=true` (the field is send-only).
- `400` — file parts present.
- `400` — `existing_message_id` doesn't point to a draft.
- `404` — `existing_message_id` not found or belongs to another user.

### `GET /api/messages/{id}/attachments`

```json
200 OK
[
  {
    "id": "uuid",
    "filename": "report.pdf",
    "content_type": "application/pdf",
    "size_bytes": 12345
  },
  ...
]
```

Excludes inline images (`is_inline=true`). Empty array if the message
has no attachments. Bytes are not included; use the download endpoint.

### `POST /api/messages/{id}/attachments` (multipart only)

Same multipart shape as compose's `attachments` part. Returns the
newly-created rows only (not the full attachment list — fetch via GET
if needed):

```json
201 Created
[
  {
    "id": "uuid",
    "filename": "report.pdf",
    "content_type": "application/pdf",
    "size_bytes": 12345
  }
]
```

Errors:
- `400` — message is not a draft (sent mail's attachment list is
  immutable).
- `400` — request was JSON, not multipart, or had no `attachments`
  parts.
- `404` — message not found / not owned by the user.
- `413` — adding the new files would push the draft's total over
  `ATTACHMENT_MAX_BYTES`. Existing attachments are counted toward the
  cap. Partial writes from this batch are unlinked from disk before
  the error returns.

### `DELETE /api/messages/{id}/attachments/{att_id}`

```
204 No Content
```

Side effects: row deleted, on-disk file unlinked (best-effort —
missing file does not fail). If this leaves the message with zero
non-inline attachments, `Message.has_attachments` flips to `false`.

Errors:
- `404` — message or attachment not found / not owned by the user.

### `GET /api/messages/{id}/attachments/{att_id}/download`

```
200 OK
Content-Type: <attachment.content_type>
Content-Disposition: attachment; filename="<sanitized>"; filename*=UTF-8''<encoded>
<bytes>
```

For Gmail-synced received attachments where `storage_path` is null and
`remote_id` is set, the endpoint lazy-fetches via the Gmail API. For
outbound (Phase 9) attachments where `storage_path` is set, reads from
`ATTACHMENT_STORAGE_DIR` via the storage layer. Either way, same wire
contract.

---

## 6. Send-failure semantics

If the provider transport (Gmail API or aiosmtplib) raises during
`send_from_draft`:

1. The draft message row stays as `is_draft=true` with all its
   attachments intact (committed before the send attempt).
2. The endpoint returns:

   ```json
   502 Bad Gateway
   {
     "detail": "Failed to send message. The draft has been saved — open it from the Drafts folder to retry."
   }
   ```

3. The frontend surfaces this as an inline error in the compose modal
   — **not as a toast**. The user needs to know their work is in
   Drafts and not lost. Modal stays open, attachments stay listed,
   Send button re-enables.

This applies equally to:
- New compose with attachments (multipart `/compose`).
- Restored draft Send (JSON `/compose` with `existing_message_id`).

The user retries by either:
- Clicking Send again (modal still open).
- Closing the modal, opening Drafts, clicking **Edit** on the saved
  draft, clicking Send.

---

## 7. Known limitations

### 25 MiB cap is on-disk size, not encoded size

Email transports base64-encode attachments, which inflates payload size
roughly **33%**. A file at exactly 25 MiB on disk becomes ~33 MiB on
the wire. Gmail enforces its limit on the **encoded** size, so files
near the cap may be rejected by the provider despite passing local
validation.

The compose modal warns at 18 MiB on-disk total ("approaching Gmail's
practical limit due to encoding overhead"), but doesn't block. Hard
stop is at the configured cap.

If you raise `ATTACHMENT_MAX_BYTES`, factor in the 33% overhead
yourself based on the destination provider's actual policy.

### No upload progress indicator

Files show "uploading…" status while in flight, but there's no per-
file progress bar. For 25 MiB caps over typical home/office bandwidth,
upload latency is small enough that this isn't acutely missed. If the
cap is raised significantly (50 MiB+) or if users on slow connections
complain, switch from `fetch` to `XMLHttpRequest` and wire
`upload.onprogress` per item.

### No streaming send

`EmailSendService` builds the entire MIME message in memory before
handing it to the transport. At 25 MiB × N attachments per send, peak
memory is bounded and fine. If `ATTACHMENT_MAX_BYTES` is ever raised
to 100 MiB+, revisit:

- `aiosmtplib.send` accepts the message object; no built-in streaming.
- Gmail API's `messages.send` takes a base64url-encoded `raw` field
  in JSON; no streaming option there either. The resumable upload
  endpoint (`upload/v1/messages/send`) supports chunks but we don't
  use it.

For our current scale (single user, 25 MiB cap), memory is not the
bottleneck and the simpler in-memory path stays.
