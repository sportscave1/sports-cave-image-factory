# Email V1 — live VentraIP inbox

Historical V1 implementation record. The current desktop mailbox and explicit SMTP actions are
documented in [EMAIL_V2.md](EMAIL_V2.md); V2 retains the mailbox-as-truth and metadata-only boundaries.

Implemented locally only. No deployment, commit, push, mailbox connection, remote migration,
Render change, DNS change, forwarding change or Resend change was performed.

## Architecture and data ownership

`app.py` imports `support_email_page` only when the selected, authorized route is Email.
The page calls the `EmailProvider` abstraction, implemented by `ImapProvider` in
`support_email_provider.py`. There is no listener, background sync or startup connection.

**VentraIP remains the sole source of truth for customer email.** IMAP provides all headers,
message text, MIME structure and attachments. No email content is written to Supabase,
SQLite, local files, logs or an application email database. Losing Supabase cannot lose mail.
No SMTP or Resend client is imported or called by this feature.

`support_email_logic.py` provides pure threading, matching and a session-memory display cache.
`support_email_store.py` reads existing `shopify_orders`, `shopify_order_lines` and
`edition_orders` and optionally reads/writes Sports Cave workflow metadata. Order reads are
bounded and read-only; they never trigger Shopify requests, schema creation or a sync.

The only changes to existing application code are Email navigation/lazy routing in `app.py`
and a worker-assignable Email entry in `os_accounts.py`. Home, Orders, Fulfilment, Edition Ops,
Mockups, Social Media, Product Uploads, Design Studio, Ads, Meta Review, Creative Refresh,
Analytics, SEO, VA Training, Certificates and Prodigi implementations are unchanged.
The existing `email_service.py` and all Resend configuration are unchanged.

## Live loading, refresh and failure handling

- Defaults: `ventraip.email:993`, SSL enabled, full mailbox address as username.
- The adapter uses `ssl.create_default_context()` to verify certificates and hostname.
- Connections have an 8-second socket timeout. Login, read-only INBOX selection and logout
  are scoped to an operation. No STORE, COPY, MOVE, DELETE, APPEND, CLOSE or EXPUNGE is used.
- The initial snapshot fetches the latest 50 message headers in one bounded FETCH. It includes
  UID, flags, INTERNALDATE, From, To, CC, subject, Date, Message-ID, In-Reply-To and References.
  Header requests use `BODY.PEEK[HEADER.FIELDS (...)]`; no message bodies are fetched for rows.
- Load More adds 50 messages, up to the newest 1,000. Counts refer to the fetched window and
  INBOX, not an invented complete conversation history. Search covers this window only.
- Entering Email starts a fresh cache scope. Repeated Email renders can reuse a 20-second
  session-memory display cache. Account, credential rotation and navigation changes isolate it.
  There is no global/disk cache and no automatic polling or IMAP IDLE.
- Refresh Inbox clears Email display entries and immediately fetches INBOX headers again.
  It does not alter flags, mail, orders or other page caches. A successful explicit refresh
  records a fixed audit event using the existing activity infrastructure.
- Expired/failed reads do not return stale mail. The page shows a safe error and the last
  successful refresh time. Optional database failures cannot prevent mailbox access.
  Cache expiry is evaluated on a render, not by a background timer.
- IMAP errors expose constant safe messages; server logs contain the exception type only.
  Credential values, provider response text and tracebacks are not logged by this feature.

Test Connection performs SSL login, read-only INBOX selection and IMAP LIST. It reports the
mailbox message count and discovered folder declarations without selecting a guessed folder.

## Threads, identity and matching

Message-ID, References and In-Reply-To relationships are joined first, including missing
ancestors. The calculated thread key is SHA-256 of the mailbox and root identity. All known
ancestor/message identities supply hashed aliases, so a saved workflow on an earlier visible
message can still resolve after Load More. Missing IDs fall back to folder + UIDVALIDITY + UID.
UIDVALIDITY is checked again before every body or attachment read, preventing UID reuse from
opening a different message after a mailbox reset.

Subjects normalize repeated Re/Fw/Fwd prefixes. Headerless reply relationships use subject
plus the full external participant set only when there is exactly one original in the prior
seven days. Independent original messages never merge merely because the customer or subject
matches. Incomplete/inconsistent headers can still produce incomplete threads. If expanded
history joins multiple saved workflows, the UI shows a conflict and disables edits rather than
choosing one silently; administrator reconciliation is a later capability.

Customer/Sports Cave labels compare the actual From address to the configured mailbox,
case-insensitively. Display names never determine message direction. This preserves the
original sender rather than treating the Resend forwarding destination as the customer.
It is correspondence identification, not independent proof of sender identity.

The table sorts by latest customer receipt time, displays actual unread flags and shows
conversations with a compact row selection. The conversation's message selector lists messages
oldest to newest; selecting one reads its text. V1 deliberately bounds each action to one
message rather than making dozens of network requests for a long thread.

Order matching uses exact normalized customer email against existing synced orders. Exact
SC-prefixed order numbers in the subject can disambiguate multiple orders or match an alternate
sender address. On opening a message, exact body references are considered when the subject
has no order number. Bare numbers, names and partial order-number substrings are never matches.
Multiple orders, multiple references and conflicting email/reference evidence remain ambiguous.
The UI shows “Multiple possible orders” or “Order reference needs review” and never chooses the
latest automatically. Matched context shows products, variants, editions, certificate state,
fulfilment, available synced tracking and other orders for that exact email. Missing synced
fields are identified as unavailable. Shopify links are HTTPS allowlisted; OS links use the
existing Orders search. “Open Edition Record” opens that order's existing edition records.

Manual order association fields are reserved in the workflow table; V1 has no association
editor. No order write actions are added.

## MIME, HTML and attachments

The Python email parser decodes MIME headers, Unicode, base64 and quoted-printable text.
Opening a message retrieves BODYSTRUCTURE first, then only readable text sections via
`BODY.PEEK[section]`. Multipart/alternative prefers plain text; multipart/mixed retains distinct
text parts. Attached messages and named/disposition attachments are never auto-downloaded.

HTML is converted to inert readable text; scripts, styles, embedded objects and image
attributes are discarded. All displayed email text is HTML-escaped inside a fixed `st.html`
container, so Markdown image syntax also cannot create tracking requests. No original HTML,
remote image, link preview or tracking pixel is rendered.

Attachment metadata comes from BODYSTRUCTURE: filename, MIME type and encoded byte size.
“Retrieve attachment” rechecks the UIDVALIDITY and MIME structure and fetches only that section
directly from VentraIP. A binary download button then serves the result from session memory.
No inline attachment execution/preview, disk write or Supabase storage is implemented.

Limits: 512 KiB encoded per text part, 12 text parts per message, 100 MIME parts, nesting depth
30, a 20-second text-read loop budget plus any in-flight socket timeout, and 15 MiB encoded per
attachment download. Oversized or malformed content displays a safe per-message notice; the
existing mail client remains available for unsupported formats. V1 does not implement encrypted
MIME, special proprietary mail formats or a virus scanner.

## Optional workflow metadata

`migrations/20260927020406_customer_support_workflow.sql` defines **only**
`public.customer_support_threads`. It has not been applied. The mailbox works without it.

Fields: id, mailbox, hashed thread_key, assigned_user_id, support_status, matched_order_id,
matched_order_number, match_method, internal_notes, needs_approval, last_handled_by,
last_handled_at, created_at and updated_at. `(mailbox, thread_key)` is unique. There are no
email headers, subjects, bodies, HTML, attachment metadata/binaries, raw messages or content
JSON columns. Internal notes are manually authored Sports Cave notes, never populated from mail.

The table uses RLS and revokes PUBLIC/anon/authenticated access. It follows the existing trusted
server-side Postgres connection and OS authorization model; no browser Data API policy is added.
Review/apply this migration separately before enabling workflow persistence. No automatic
schema provisioning occurs when Email loads. OS account/order tables must already exist.

Statuses: Needs Reply, Waiting on Customer, Waiting on Sports Cave, Resolved. Unsaved
conversations show a clearly labelled Needs Reply triage default. Summary totals include saved
decisions only, not inferred historical status. Assignment lists active existing OS accounts with
Email access, including Nathan/Reina where configured. Page permissions and assignment validity
are enforced again at the save boundary. Concurrent updates use an updated_at check and ask
the user to refresh rather than overwriting another user's decision.

Status, assignment, note and approval changes reuse the existing audit facility with fixed
descriptions and hashed thread identifiers. Email text and note text are absent from audit
payloads. These actions do not move, archive or alter mailbox flags.

## Render variables Nathan must add manually

Add these to the existing canonical **sports-cave-os** service (`srv-d8kl4on7f7vs73dvavv0`)
only when ready to test the locally reviewed implementation:

```dotenv
SPORTSCAVE_EMAIL_IMAP_HOST=ventraip.email
SPORTSCAVE_EMAIL_IMAP_PORT=993
SPORTSCAVE_EMAIL_ADDRESS=hello@sportscaveshop.com
SPORTSCAVE_EMAIL_PASSWORD=<the mailbox password, entered privately in Render>
SPORTSCAVE_EMAIL_IMAP_SSL=true
```

Do not paste the password into Codex, source code or this document. No SMTP variable or Resend
key is needed for Email V1. Existing database variables are reused only for optional context
and workflow. Do not create a service, change render.yaml, or modify MX/DNS/mailbox/forwarding.

## Manual acceptance procedure for hello@sportscaveshop.com

1. Review the local diff and this document. Authorize deployment/testing separately; this task
   has not deployed or connected to the mailbox. Keep the existing webmail client available.
2. Nathan privately configures the five variables in the intended test runtime. If testing on
   Render, use the existing primary service after a separately authorized deployment. Do not
   change mailbox settings, Resend, forwarding, DNS or MX records.
3. Sign in as Nathan. Grant Reina Email access through existing Accounts & Access if wanted.
   Verify an account without Email permission cannot open `?page=email`.
4. Open Home and Orders before Email. Confirm normal behavior and no IMAP operation. The
   automated full-app fixture verifies this with a forbidden-real-IMAP guard.
5. Open Email. Confirm the address, Live mailbox indicator, VentraIP source and refresh time.
   Compare the newest 50 headers/senders/times/flags against INBOX in webmail. Search by a
   customer, subject and matched order; Load More should expose 50 older messages.
6. Click Test Connection. Expect a successful read-only INBOX check and the real mailbox count.
   Inspect discovered folder names if useful; V1 still reads only INBOX.
7. Open an existing unread message/thread. Check Unicode names, To/CC, subject, Date,
   Message-ID/References, text and original headers. Verify webmail still shows the same unread
   state. Review multiple messages oldest to newest; missing Sent replies must not be invented.
8. Open existing plain, HTML-only, alternative and mixed messages. Confirm readable text and no
   remote image/tracking loads. Check attachment names/types/encoded sizes; only clicking
   Retrieve attachment should fetch its bytes. Download and compare one known attachment.
9. Compare matched order context with the existing order system. Check an exact-email case,
   a different-sender order-number case and a customer with multiple orders. Ambiguity must
   remain visible with no selected order. No order write controls should exist.
10. Let a naturally arriving email appear in webmail (no send action is provided here). Click
    Refresh Inbox and verify it appears. Check that the OS did not change any real mailbox flags.
11. With workflow migration absent/database unavailable, confirm inbox access still works.
    After separate migration approval/application, save a test status, assignment and internal
    note; reopen in another session. Confirm only workflow fields/audit descriptions were saved,
    and the mailbox message remains unchanged. Test concurrent edits in two sessions.
12. In an isolated test runtime, use a deliberately invalid credential or block IMAP temporarily.
    Refresh: expect a restrained connection error and last-success timestamp, no stale rows and
    no leaked credential. Home and Orders must still work. Restore privately and refresh.
13. Inspect the real mailbox for unchanged flags/counts/content and review logs for safe error
    types only. Nathan signs off before any production release or Email V2 work.

## Verification and release position

Automated tests use mocks only. See `tests/test_support_email.py`: 49 tests passed, including
full app boot/Home/Orders/Email route isolation, TLS, parsing, multipart handling, attachment
gating, UIDVALIDITY, threading, ambiguity, cache refresh/expiry, failure isolation, HTML safety,
permissions, metadata-only writes, workflow editing and optimistic concurrency.

Existing regression modules run in separate processes (to avoid existing bare Streamlit
import/form-state contamination): startup scope 6, navigation performance 23, sidebar cleanup 5,
grouped routing 7, accounts 79, bounded order reader 7, Orders UI 137, Home 133, existing Resend
email service 6 and Render topology 3. **404 passed; two unrelated existing assertions failed**
in `test_orders_loading_ui`: `test_mockups_prompt_cards_use_compact_modal_prompt_actions` and
`test_product_uploads_shows_only_selected_embedded_product_prompt`. Both also fail when the
tests read unchanged `HEAD:app.py`; their implementation was not modified.

SQL syntax was parsed with pglast; the migration was not executed against Postgres. All changed
Python files were compiled and `git diff --check` was run. No real credentials or mailbox were
used. Logs of the local checks are under ignored `output/`.

Safe to begin supervised, read-only mailbox testing: **yes**, within the stated limits.
Production readiness: **conditional**, pending real VentraIP authentication/TLS/MIME checks,
manual acceptance, optional workflow migration validation and Nathan's release approval.
No VentraIP-specific behavior was verified live; folder naming, server quirks and actual mailbox
cardinality remain unverified. Sent history is intentionally not included.

Email V2 recommendation: editable Draft Reply, explicit SMTP sending, send confirmation,
VA approval permissions/queues, safe sender/recipient validation, idempotency and sent-mail
reconciliation. None of Email V2 is implemented or enabled.

Implementation references: [Python IMAP documentation](https://docs.python.org/3/library/imaplib.html)
for read-only selection/TLS/UID semantics, and [Supabase API security](https://supabase.com/docs/guides/api/securing-your-api)
for table access and RLS separation.
