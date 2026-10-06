# Email Inbox hardening — local implementation, 6 October 2026

## Findings and actual architecture

The Inbox uses **VentraIP IMAP over TLS (993) and authenticated SMTP over TLS
(465)**. It does not send through Resend. Campaigns/automations use separate
infrastructure and were not modified. Authentication is mailbox-password based;
there is no Gmail history API or OAuth refresh flow to repair here.

Existing useful architecture was retained:

- `support_email_page.py` renders a Streamlit fragment and the existing custom
  JavaScript component. Component events preserve the surrounding OS page.
- `support_email_reads.py` owns bounded asynchronous reads, coalesces concurrent
  requests, and publishes a 50-header Inbox snapshot. `support_email_snapshot.py`
  persists that bounded metadata/cursor in Supabase. It is a mailbox cache, **not
  a complete local replica of every historical message**.
- `support_email_provider.py`, `support_email_transport.py`, and
  `support_email_runtime.py` own timed, short-lived IMAP connections, connection
  budgets, transient read retries, cooldowns, flags, folders, searches and lazy
  message/attachment fetching. There are no reused stale IMAP sockets.
- `support_email_idle.py` runs an ASGI-lifecycle IDLE watcher with a database lease
  and the existing polling fallback. The Inbox read service starts independently
  of a browser. Top-bar notifications use the existing shared scheduler.
- Search is server-side IMAP SEARCH, with bounded header results/load-more. Opening
  one message fetches only its MIME parts; it does not download the whole mailbox.
- Reply/Reply All/Forward, CC/BCC, signatures, attachments, folders and CRM/order
  context use their existing paths. CRM/order enrichment remains explicit.
- Received HTML uses the existing sanitizer and sandboxed reader.

Root causes found in code:

1. SMTP intents, receipts and Sent-APPEND guards were process-local. A browser or
   process interruption could lose the only local evidence of delivery/copy state.
2. A positive Message-ID match in Sent did not promote an uncertain send to
   accepted. The UI could remain uncertain despite useful evidence.
3. SMTP can time out after DATA was accepted. The transport correctly did not
   blindly resend, but lacked durable background reconciliation.
4. Accepted sends synchronously waited for IMAP copy/refresh work. IMAP trouble
   therefore delayed a successful send's final UI state.
5. Draft edits lived in session/browser state until an explicit IMAP Save draft.
   There was no durable debounced autosave or protection against stale-tab writes.
6. Some background action acknowledgements could repaint the composer. The
   nondestructive rendering exemption did not cover all relevant events.
7. Connected health could remain stale; Inbox synchronization had a process lock
   but no shared index lease, and duplicate header rows were not normalized at
   both snapshot and threading boundaries.

**Not verified against production:** the cause of particular VentraIP outages
or the Ian/Australia Post EZ Label Support rows. Local IMAP/SMTP credentials are
not configured. Similar sender/subject/time is insufficient evidence of duplicate
ingestion, so no production records were deduplicated or deleted.

## Changes

### Durable delivery

`support_email_durable.py` stores the exact MIME, recipients, stable operation
UUID/Message-ID and fingerprint **before** contacting SMTP. A database claim
permits only one sender across processes. Retrying the same operation cannot
substitute different MIME or send again after a non-queued state.

States are `queued → in_progress → accepted / rejected / unknown`.
Accepted is committed on the positive DATA acknowledgement, before SMTP cleanup.
An abandoned in-progress claim becomes unknown, never queued again.

Confirmed transient rejection or a network failure before DATA can return to
queued, with at most three transport attempts and exponential cooldown plus jitter
(approximately 30s, then 60s). The UI and worker honour the persisted due time.
Authentication/permanent rejection requires review. Ambiguous DATA **never**
automatically retries. SMTP 4xx/5xx semantics are used, not HTTP semantics; there
is no HTTP 429/Retry-After transport in this Inbox.

The lifecycle-owned outbox worker processes persisted work without an open page,
with database claims, bounded reconciliation and worker-error backoff. No Render
service or competing campaign queue was created.

Uncertain sends are searched by their exact RFC Message-ID in the configured Sent
folder. Positive evidence marks accepted. Absence is not evidence of rejection.
The worker performs up to six reconciliation attempts; the UI also performs
bounded read-only checks, then offers manual **Check Sent copy**. There is no
resend action for uncertain mail. If VentraIP accepted DATA but does not store a
Sent copy, an administrator may need provider delivery logs: SMTP itself supplies
no idempotency/retrieve-send API that could safely prove this outcome.

Accepted messages immediately show a readable, sanitized **View sent message**
receipt from the local ledger, including after reload. Remote Sent storage runs
separately. Sent-copy APPEND intent is persisted before IMAP; an interrupted
APPEND is searched, not repeated. A known pre-APPEND rejection can retry.
The remote Sent view still uses IMAP; it may lag the local accepted receipt during
an IMAP outage. No synthetic remote UID is invented.

### Drafts and rendering

- Autosave after 1.5 seconds without an edit, with Saving/Saved/failure feedback.
- Recipients, subject, sanitized body, attachment bytes, signatures and reply
  references are private database state, scoped to mailbox and OS account.
- Optimistic revision checks reject stale-tab overwrites; discard leaves a
  tombstone so an old tab cannot resurrect the draft.
- Saved drafts restore after reload/restart. Drafts also lists recent local
  autosaves for reopening. Accepted drafts cannot restore as unsent.
- Background sync, reconciliation and autosave acknowledgements preserve the
  existing composer DOM, selection and focus. Edits during an in-flight autosave
  schedule another save and do not get replaced by the older acknowledgement.
- The last unfinished debounce interval is not guaranteed across an immediate
  browser/process kill. The indicator does not claim those edits are saved.

### Inbound, health and diagnostics

- Incremental UID + UIDVALIDITY synchronization and persisted cursors retained.
- Shared database lease added for index sync, with newer persisted snapshots
  adopted by a follower. Snapshot UPSERT retains its existing stale-write fence.
- Exact `(folder, UIDVALIDITY, UID)` repeats collapse to one header. Different
  provider identities remain separate; no sender/subject-based deduplication.
- RFC Message-ID, References and In-Reply-To threading retained. The existing
  conservative fallback requires matching participants, a unique original and a
  seven-day window; it is not subject-only. IMAP exposes no provider thread ID.
- Connected expires after 180 seconds without a successful sync. Configuration,
  last sync, authentication freshness, database verification and local read-worker
  status are separate diagnostics. Syncing does not show a connected green dot.
- Admin-only Email settings diagnostics show inbound health and persisted outbound
  state counts/latest attempt. Logs include safe operation/sync IDs, durations,
  attempts and error categories; never passwords or message bodies.

## Schema and deployment prerequisite

New additive migration:
`migrations/20261006063028_support_email_durable_delivery.sql`.

- Private `support_email_drafts`, primary key `(mailbox, actor, draft_id)`, partial
  recent-active-draft index.
- Private `support_email_outbox`, primary key `(mailbox, operation_id)`, unique
  `(mailbox, message_id)`, due-work index.
- RLS enabled; PUBLIC/anon/authenticated access revoked; payload size bounded.
- Existing migration history and SHA validation remain intact. No tables dropped,
  no production migration applied and no historical mail changed.

Apply through the existing reviewed deployment migration mechanism **before
testing sending/autosave against the real application database**. Missing durable
storage fails closed rather than falling back to an unrecorded SMTP send.

No new environment variables or Render services are required. The existing ASGI
server needs the existing database connection and these existing mailbox keys:

`SPORTSCAVE_EMAIL_ADDRESS`, `SPORTSCAVE_EMAIL_PASSWORD`,
`SPORTSCAVE_EMAIL_IMAP_HOST`, `SPORTSCAVE_EMAIL_IMAP_PORT`,
`SPORTSCAVE_EMAIL_IMAP_SSL`, `SPORTSCAVE_EMAIL_SMTP_ADDRESS`,
`SPORTSCAVE_EMAIL_SMTP_PASSWORD`, `SPORTSCAVE_EMAIL_SMTP_HOST`,
`SPORTSCAVE_EMAIL_SMTP_PORT`, `SPORTSCAVE_EMAIL_SMTP_SSL`.

SMTP and IMAP must refer to the same mailbox. Confirm the existing Sent-folder
mapping and server-vs-client Sent-copy policy. Standalone Streamlit is not the
background worker host; normal production runs through `sports_cave_server.py`.
No Render environment variables were read, changed or exposed for this work.

## Validation and measured performance

Offline profile command:
`.venv/Scripts/python.exe -X utf8 -m tests.profile_email_interactions`.
These are fabricated-provider timings, **not production network latency**:

| Operation | Before ms | After ms | Provider calls |
|---|---:|---:|---|
| Fixture initial mailbox | 2.552 | 2.471 | Same folders/header/selected-body calls |
| Cached open | 0.011 | 0.012 | 0 both |
| Reply | 0.146 | 0.164 | 0 both |
| Live delta | 0.358 | 0.189 | 1 lightweight delta both |
| Search | 1.345 | 1.569 | 1 server-side header search both |

Small CPU differences are noise, not claimed speed improvements. The meaningful
send-path improvement is removing all IMAP calls from durable accepted-send
finalization. Receipt polling reads metadata columns, not frozen MIME attachments.

Reproducible offline test commands:

```powershell
node tests/email_durable_postgres.mjs
# Separate terminal; this opt-in uses ONLY disposable PostgreSQL on 127.0.0.1:8879.
$env:EMAIL_TEST_POSTGRES='1'
.venv/Scripts/python.exe -X utf8 scripts/test_email_reliability.py
.venv/Scripts/python.exe -X utf8 -m unittest tests.test_email_durable_delivery -v
.venv/Scripts/python.exe -X utf8 run_migrations.py --deploy --check
```

The SQL migration is applied twice in the fixture. Tests exercise concurrent
claims, exact MIME preservation, positive/negative reconciliation evidence,
database failures before/after SMTP, restart recovery, bounded retry, ambiguous
APPEND, draft attachments/context/actor isolation/revisions, persisted index
leases/cursors, duplicate provider rows, stale health and HTML safety.

Final focused gate: **457 Python tests run, 454 passed, 3 skipped; all 11
JavaScript test files passed**. The 21 durable PostgreSQL tests all passed with
the fixture enabled. Changed Python files compile, JavaScript syntax checks pass,
`git diff --check` passes, and `run_migrations.py --deploy --check` returns READY.

Browser fixture (all SMTP/IMAP are fakes):

```powershell
$env:EMAIL_TEST_POSTGRES='1'
.venv/Scripts/python.exe -X utf8 -m streamlit run tests/fixtures/email_desktop_preview.py --server.port 8514
node tests/email_hardening_browser.cjs
```

Playwright requires the available Node dependency path and installed Chrome.
1440×900 browser checks passed: composer DOM/focus/caret through background
refresh, SQL autosave, reload restoration, Drafts reopening, mocked SMTP accepted
receipt, and receipt restoration after reload. Zero JavaScript runtime errors;
no real message sent. Screenshot: `output/email-hardening-composer.png`.

Full-repository unittest results are not green: **4,908 run; 4,194 passed;
184 failures; 67 errors; 463 skipped**. Baseline comparison reproduced all 251
failing case identities on untouched HEAD; the exported baseline additionally
had two path/fixture errors. The final comparison found **zero new failing case
identities**. Many failures involve existing Streamlit form fixtures and unrelated
areas. Those were not changed to make this task's results look green.

## Files changed

Runtime: `support_email_durable.py` (new), `support_email_workspace.py`,
`support_email_smtp.py`, `support_email_reads.py`, `support_email_idle.py`,
`support_email_logic.py`, `support_email_schema.py`,
`components/support_email/mail.js`, `run_migrations.py`.

Migration: `migrations/20261006063028_support_email_durable_delivery.sql` (new).

Tests: `tests/test_email_durable_delivery.py` (new),
`tests/test_email_autosave_component.cjs` (new),
`tests/email_durable_postgres.mjs` (new), `tests/email_hardening_browser.cjs` (new),
`tests/test_email_inbox_reliability.py`, `tests/test_email_live_component.cjs`,
`tests/test_email_send_status.cjs`, `tests/fixtures/email_desktop_preview.py`.

Documentation: this file.

Safe for local fixture/manual testing. Real-mailbox acceptance remains a separate
check after the migration and with an internal test recipient. No commit, push,
deployment, live email, production data change, or unrelated feature edit occurred.
