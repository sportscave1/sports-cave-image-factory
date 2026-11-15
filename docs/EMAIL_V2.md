# Email V2 — live mailbox desktop client

Implemented locally. **No commit, push, deployment, remote migration, real mailbox connection,
real SMTP submission, Render/environment modification, DNS, MX, forwarding or Resend change.**
The existing V1 routing remains unchanged. This document supersedes the read-only product
scope in `EMAIL_V1.md`; V1 parsing, threading, order matching and memory cache remain in use.

## Files changed

- Modified: `support_email_page.py`, `support_email_provider.py`, `support_email_store.py`,
  `tests/test_support_email.py`, `docs/EMAIL_V1.md` (historical-document pointer only).
- Added services/controller: `support_email_compose.py`, `support_email_smtp.py`,
  `support_email_workspace.py`.
- Added interface: `components/support_email/index.html`, `components/support_email/style.css`,
  `components/support_email/mail.js`.
- Added unapplied schema: `migrations/20260927025319_customer_support_email_settings.sql`.
- Added validation: `tests/test_support_email_v2.py`, `tests/email_v2_fixtures.py`,
  `tests/test_support_email_component.cjs`, `tests/fixtures/email_desktop_preview.py`.
- Added documentation: `docs/EMAIL_V2.md`. Ignored local test logs and a fabricated-data
  screenshot are under `output/`; no actual customer mailbox content was saved there.

`app.py`, `os_accounts.py`, `support_email_logic.py`, `email_service.py`, requirements,
Render configuration, and all unrelated OS modules are unchanged in this V2 diff.

## Architecture and ownership

`app.py` → lazy `support_email_page.render_page(current_os_user())` → Streamlit fragment →
local HTML/CSS/JavaScript component → validated `Workspace` events → IMAP/SMTP providers.

- **VentraIP is the email source of truth**, including Inbox, Sent, Drafts, Archive, Junk,
  Trash and selectable custom folders. There is no mailbox sync database or background listener.
- `support_email_provider.py` uses verified TLS IMAP on port 993, an eight-second socket
  timeout, read-only SELECT and BODY.PEEK for all reads. Explicit flag, move and append methods
  are separate. No permanent deletion, EXPUNGE or CLOSE call is implemented.
- `support_email_smtp.py` uses verified TLS SMTP on port 465 with a twelve-second socket
  timeout. Only an explicit Send event calls SMTP. No Resend integration is involved.
- `support_email_compose.py` creates recipient lists, safe rich text, signatures and MIME.
- `support_email_workspace.py` owns per-session UI state, cached display data and action IDs.
- `support_email_store.py` stores workflow/configuration only and reads existing synced orders.
  It never accepts customer MIME, email body fields, draft bodies or attachment binaries.
- Email bodies, headers, draft MIME and attachment bytes exist only in mailbox storage and
  temporary application/browser memory. They are not persisted to Supabase, application files
  or logs. Explicit downloads save only when requested by the user in their browser.

The new, **unapplied** migration is
`migrations/20260927025319_customer_support_email_settings.sql`. It adds:

1. `customer_support_email_settings`: mailbox, sender display name, three administrator-authored
   signature configurations (HTML/plain fallback), discovered folder mappings, Sent policy, timestamp.
2. `customer_support_email_preferences`: mailbox, existing `os_users` ID, signature key, timestamp.

Both tables enable RLS and revoke PUBLIC/anon/authenticated access, following V1's trusted
server-side Postgres connection and OS authorization pattern. The existing
`customer_support_threads` table continues to hold status, assignment, internal notes and approval
metadata only. Migrations are never run during page rendering. Missing settings storage leaves
live mail and built-in signatures usable; settings cannot be saved until the migration is applied.

## Desktop interaction

The compact top toolbar contains Email, New mail, submitted mailbox search, Refresh and Settings.
One small status line shows the live source, mailbox, last refresh and action result.

The component fits the remaining viewport beneath the existing OS navigation. Its grid has a
184–194 px folder pane, 360–390 px conversation pane and the remaining reading/compose pane.
Each pane scrolls independently. Rows are 68 px, with actual unread state, sender, subject,
received time, optional bounded snippet, attachment indication and star. No dashboard cards or
wide data table precede the inbox. Folders can collapse; below 680 px, reading replaces the list
with a Back control. The layout does not inject global styling into other OS pages.

The Customer / Order panel temporarily replaces the reading pane. It reuses conservative V1
matching and existing `shopify_orders`, `shopify_order_lines` and `edition_orders` data. No Shopify
API call occurs on Email render. Multiple plausible orders remain **Multiple possible orders**;
the app does not choose silently. Product/variant, edition/certificate state, fulfilment, tracking,
previous orders and read-only order/module links appear when available. Edition links open the
existing Edition Ops route; V2 does not add a new direct edition-record routing mechanism.

## Live loading, refresh and search

- Initial entry discovers folders with IMAP LIST. INBOX is identified by its protocol name;
  Sent/Drafts/Archive/Junk/Trash use unique SPECIAL-USE flags. No English folder name is guessed.
  When flags are absent or ambiguous, Nathan can map an observed LIST name in Email settings.
  Conflicting role mappings disable the ambiguous actions. Nonselectable folders are omitted.
- Real unread counts are requested using STATUS UNSEEN for up to six special folders under a
  short time budget. Missing counts stay blank. Modified UTF-7 labels are decoded for display;
  exact discovered wire names are retained and quoted for IMAP commands.
- The selected folder initially fetches its newest 50 message headers. Load More adds 50 up
  to 1,000. Counts refer to the loaded/search window, not a pretend complete conversation index.
- Optional snippets read at most the first 1,024 encoded bytes of a safe text MIME section
  for the newest 50 messages, in bounded batches. They never fetch attachment sections.
- Full readable text and attachment metadata load on explicit conversation/message selection.
  Older messages stay collapsed. Incoming HTML becomes inert readable text with safe external
  links; quoted history can be expanded separately. No remote images or tracking pixels load.
- Display reads use the existing **20-second session-memory cache**. It is not a background
  polling interval. Idle panes retain their labelled last-refresh view until another read or
  Refresh. Folder/search actions consult this short cache; entering Email again and Refresh
  invalidate it. Refresh clears Email display entries and reads LIST/headers from IMAP again.
- Search submits a real IMAP UID SEARCH against the **current folder**, including historical
  mail outside the initial 50. Plain searches use TEXT; `from:`, `to:`, `subject:` and `text:`
  prefixes select specific fields. Unicode uses CHARSET UTF-8. Only matching headers are fetched;
  bodies are not downloaded to perform search. Date bounds exist at service level, not in V2 UI.
- A selected conversation performs bounded header searches in the current folder plus discovered
  Inbox and Sent. Message-ID, In-Reply-To and References establish relationships; V1's conservative
  subject/participant fallback applies only when header evidence is missing. Duplicate Message-IDs
  across folders display once. Actions initially target the message from the selected folder;
  clicking another message changes the action target, whose folder/date is shown explicitly.
- Related-history searches use up to eight identifiers and at most 100 headers per folder.
  They are not a guarantee that every message in a very large or broken-header conversation is
  present. Headerless Sent messages cannot be found globally by reliable relationships.

Mailbox failures leave other OS modules working. Failed folder refreshes hide the old inbox
content and show a compact connection error. Existing runtime compose text is preserved. Logs
include operation/error class only, never raw provider replies, credentials or customer content.

## Compose, replies, signatures and attachments

New mail, Reply, Reply All and Forward replace the reading pane. From is fixed to the configured
mailbox; To, CC, BCC and Subject are editable. Bold, italic, underline, safe links, bullets and
numbered lists are supported. Pasted content is converted to plain text before insertion; the
server sanitizes the resulting HTML again. MIME always includes text/plain and text/html parts.

Replies preserve In-Reply-To and References. Reply uses Reply-To when present. Reply All includes
the original sender and relevant To/CC recipients, excludes the Sports Cave mailbox, and deduplicates
case-insensitively. Replying to a Sports Cave sent message targets its original recipients. BCC is
envelope-only for outgoing mail and is not exposed in outgoing MIME or a Sent copy. Forward quotes
original From/Date/To/CC/Subject/content without inventing reply headers. Original attachments are
offered for explicit retrieval/inclusion. The quoted original remains available while composing.

Company, Nathan and Reina signatures have safe HTML and plain text fallbacks. Existing OS accounts
select their own default; Nathan/admin can edit the mailbox signatures and sender name. The signature
is kept separate from editable text, inserted exactly once when building MIME. Reopened mailbox drafts
already contain their signature and default to No signature to avoid doubling it. Remote logos are
intentionally unsupported because the component blocks all images and automatic network resources.

Outgoing uploads live in session memory: **10 MiB per file, 14 MiB total, 15 files, 20 MiB encoded MIME,
25 recipients**. SMTP's advertised SIZE limit is also checked when available. Attachment chips allow
removal. Incoming attachments remain lazy, use safe filenames, and download as octet-stream rather
than executing HTML in the app; the existing 15 MiB encoded incoming-part bound remains. No antivirus
scanning, image preview or permanent attachment storage is added.

Ctrl+Enter activates the same guarded Send control, Esc closes the composer while retaining its runtime
draft, and R/F open Reply/Forward when focus is outside an input. Closing/reloading the browser or a
server restart can lose unsaved runtime drafts; use Save draft for mailbox persistence.

## Sending and duplicate protection

Each compose session has a UUID send-operation ID before the first click, carried by the client Send
event and used in the deterministic Message-ID. The browser disables actions immediately and remembers
submitted operation IDs. The controller records event IDs before effects; the process-wide locked
SendRegistry claims the operation before networking. Streamlit fragment reruns and concurrent repeated
events cannot resubmit that operation. Receipts contain only status, Message-ID and a MIME hash.

SMTP authenticates, checks MAIL FROM and every RCPT TO, and sends DATA only when all recipients are
accepted. Recipient refusal resets the SMTP transaction before sending anything. Success is displayed
only after DATA returns 250. A disconnect/timeout during DATA is **unknown**, locks the composer and
never automatically retries. A known rejection permits an explicit Prepare again with a fresh ID.
QUIT failure cannot turn an accepted send into a failure/retry. Acceptance means server acceptance,
not proof of final recipient delivery.

The registry is process-memory, not durable distributed exactly-once delivery. A browser/session loss,
server restart or multiple independent server processes cannot preserve all operation receipts. After
an interrupted session, Nathan must inspect the real Sent mailbox and recipient before manually
recomposing. Do not scale sending across multiple processes without a shared metadata-only receipt
design. No automatic network retry or background send is implemented.

Replies/forwards re-read their original workflow aliases before sending; known approval requirements
or conflicting workflow records block a worker, and a metadata outage blocks worker replies. Nathan/admin
can review and send. Workers cannot clear a recorded approval requirement. This is basic conversation
protection, not a full approval queue or organisation-wide restriction on every newly composed message.

## Sent and Drafts

Sent is discovered or explicitly mapped, never assumed. After SMTP acceptance, the app searches the
actual Sent folder by Message-ID and verifies complete header equality (IMAP search itself matches
substrings). Existing copies are not appended again.

The default Sent policy is **verify**. VentraIP's automatic Sent behavior cannot be determined without
an authorized supervised real send, which was deliberately not performed. If Nathan confirms automatic
saving, choose **Server saves Sent**. If he confirms SMTP does not save it, choose **App saves Sent**;
this enables one IMAP APPEND of the final MIME after an exact-ID check. An uncertain APPEND is recorded
and never blindly repeated. Check Sent performs verification without SMTP. The default therefore may
leave an accepted test message without a Sent copy until the server behavior/policy is established.

Drafts support explicit Save draft, editing an existing mailbox draft, another saved revision and
discard to mapped Trash. No autosave. Draft MIME includes BCC, signature, attachments and reply headers.
Each saved revision has its own stable Message-ID. APPEND is claimed once; uncertain saves can only
be checked again, and editing/sending/discarding is blocked while unresolved. A new revision is verified
before the old one is moved to Trash. After SMTP acceptance, a saved draft is also moved to Trash when
possible. Failure to remove an old draft is reported; the accepted email is never sent again to fix it.

## Flags and moves

Read/unread and Star use real UID STORE for `\\Seen` / `\\Flagged` only. Opening mail is still BODY.PEEK
and does not mark it read. UIDVALIDITY is checked before UID-based reads/writes, avoiding a stale UID
being applied to a different message after mailbox recreation.

Archive, Trash and Junk use UID MOVE when advertised. **No permanent deletion or EXPUNGE is present.**
When MOVE is unavailable, the fallback is COPY only, with a clear **original retained** notice. It does
not claim the original was removed. That also means old draft versions remain on such servers and must
be cleaned up through the existing mail client. A mailbox with no safe destination mapping disables
that operation. No spam training is implemented.

## Manual environment setup (Nathan only, not performed)

Retain the working V1 variables:

```dotenv
SPORTSCAVE_EMAIL_IMAP_HOST=ventraip.email
SPORTSCAVE_EMAIL_IMAP_PORT=993
SPORTSCAVE_EMAIL_ADDRESS=hello@sportscaveshop.com
SPORTSCAVE_EMAIL_PASSWORD=<existing Render secret>
SPORTSCAVE_EMAIL_IMAP_SSL=true
```

Add these five variables manually to the existing canonical `sports-cave-os` Render service:

```dotenv
SPORTSCAVE_EMAIL_SMTP_HOST=ventraip.email
SPORTSCAVE_EMAIL_SMTP_PORT=465
SPORTSCAVE_EMAIL_SMTP_SSL=true
SPORTSCAVE_EMAIL_SMTP_ADDRESS=hello@sportscaveshop.com
SPORTSCAVE_EMAIL_SMTP_PASSWORD=<Render secret>
```

SMTP credentials are read separately; the application does not copy/fall back to the IMAP password.
Do not paste passwords into Codex, signature settings, test fixtures or logs. No mailbox secret is
stored in Supabase or passed to the component. No Render configuration file or environment was edited.

## Supervised acceptance sequence after an approved deployment

1. Nathan reviews the local diff, applies the V2 metadata migration using the existing trusted
   migration process, and authorizes deployment to the **existing** canonical service. No replacement
   service. Add the SMTP variables manually. Keep Thunderbird/webmail available during acceptance.
2. Visit Home and Orders first. Confirm normal behavior and absence of IMAP/SMTP startup activity.
   Enter Email and compare its latest Inbox senders/subjects/dates against VentraIP webmail.
3. Open Settings → Test IMAP connection. Inspect LIST-discovered folders and actual unread counts.
   Map missing/ambiguous Sent, Drafts, Archive, Junk and Trash using verified webmail folder identities.
   Keep Sent policy at Verify only initially. Confirm MOVE support during disposable-message testing.
4. At a 1440+ desktop, check the three panes, independent scroll, Load More, folder collapse and
   customer/order drawer. Open an unread test message and confirm it stays unread in webmail.
5. Search an older known subject/order reference/email outside the newest 50. Check `from:` and
   `subject:` plus a Unicode name. Verify Inbox/Sent switching and refresh after receiving a test message.
6. Create a uniquely titled test message **to Nathan's own controlled test address**, with a harmless
   small attachment, CC/BCC test addresses he controls, formatted text and his signature. Save draft;
   verify body, signature, BCC, attachment and Draft flag in the actual Drafts folder. Reopen/edit/save
   another revision. Confirm the previous revision moved to Trash rather than being expunged.
7. Press Send once. Wait for SMTP acceptance. Verify exactly one delivered message, safe formatting,
   the correct From, no leaked BCC, one attachment, and the expected Message-ID. Verify whether the real
   Sent folder acquired a copy automatically. Refresh/check again to account for delayed server filing.
   **Do not resend** merely because the Sent copy is absent or the UI lost connection.
8. If the server stores Sent, select Server saves Sent. If it does not, select App saves Sent. Send a
   second uniquely titled test message to the controlled address and verify exactly one Sent copy and
   one received message. Repeated Check Sent/Refresh must not create another copy. Verify across a
   normal Streamlit interaction/rerun. Do not deliberately interrupt a production send to test timeouts.
9. Reply, Reply All and Forward using only controlled correspondents. Confirm exclusion of the support
   mailbox in Reply All, recipient deduplication, threading in Thunderbird/webmail, original quoted
   context, optional forwarded attachments and signature appearing once. Compare Inbox + Sent history.
10. On disposable test messages only, test Mark read/unread, Star/unstar, Archive, Trash and Junk. Check
    each change in webmail. If COPY fallback is reported, verify the original remains and retain
    Thunderbird for cleanup; do not treat the operation as a completed move.
11. Verify Nathan/Reina signatures and own-user preferences; test workflow status/assignment/notes,
    ambiguous order matching, and worker approval blocking. Internal notes must never appear in MIME.
12. Download an incoming test attachment, open a test HTML email containing remote imagery, and confirm
    no images load automatically. Test a harmless oversized upload and invalid recipient locally in
    the composer: useful errors, preserved body text, and no send until corrected.
13. Confirm normal mailbox refresh/reconnection, and inspect sanitized server logs. Test outage handling
    with the local fixture rather than interrupting live credentials or production networking.
14. Only after all checks pass should Reina trial daily correspondence alongside Thunderbird. Retain
    Thunderbird until Sent filing, Draft cleanup, folder mapping, server size limits, search charset,
    MIME variants, recipient delivery and the exact deployed viewport are verified.

## Validation and readiness

Run shared Email and V2 tests in separate processes from whole-app regression suites:

```powershell
.venv/Scripts/python.exe -m unittest tests.test_support_email -q
.venv/Scripts/python.exe -m unittest tests.test_support_email_v2 -q
node tests/test_support_email_component.cjs
.venv/Scripts/python.exe -m streamlit run tests/fixtures/email_desktop_preview.py --server.port 8503 --server.headless true
```

The preview harness injects mailbox/SMTP/database/audit doubles, blocks real IMAP/SMTP constructors,
and contains only fabricated customer data. It never reads mailbox credentials. Do not use `app.py`
with live credentials as an automated test target.

Recorded local results: **45 shared Email tests + 57 V2 tests passed**, plus 10 component helper
assertions. A real browser exercised the mock conversation, Reply All, body entry, Save Draft and
Send; accepted sends disable Send and display Sent verification separately. The desktop viewport was
measured with independent pane columns and no page overflow in the fixture. Smaller-width rendering
was also inspected. Final syntax, compile and diff checks are recorded in the completion report.

Existing regression suites: **404 passed / 2 pre-existing failures** across 406 tests:

| Suite | Result |
|---|---:|
| app startup scope | 6 passed |
| navigation performance | 23 passed |
| sidebar cleanup | 5 passed |
| grouped submenu routing | 7 passed |
| OS accounts | 79 passed |
| bounded order reader | 7 passed |
| Orders loading UI | 135 passed, 2 pre-existing failures |
| Home dashboard | 133 passed |
| existing Resend email service | 6 passed |
| Render topology | 3 passed |

The two failures are `test_mockups_prompt_cards_use_compact_modal_prompt_actions` and
`test_product_uploads_shows_only_selected_embedded_product_prompt`. Both reproduce when the tests
read **HEAD's unmodified app.py**. They were not changed as part of Email work.

**Ready for a controlled deployment and supervised acceptance, not yet certified to replace
Thunderbird.** Live VentraIP capabilities, actual folder names, automatic Sent behavior, SMTP delivery,
server limits and production viewport integration remain unverified. No live provider limitation is
claimed as observed; these are explicitly untested. The conservative COPY fallback and process-memory
send receipt scope are known implementation limits. No CRM, automated replies or Email V3 was started.
