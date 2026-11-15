# Email V2.3 — local implementation and validation

27 September 2026. Starting and finishing HEAD: `d575b1a` (Email performance pass).
No commit, push, deployment, Render change, database mutation against Supabase,
mailbox authentication, message send, or real mailbox mutation was performed.

## Capability and topology evidence

- A verified TLS connection to `ventraip.email:993` returned `OK` to a read-only,
  **pre-login CAPABILITY** probe and advertised **IDLE**. The connection was closed.
- Local mailbox credentials were not configured. Authenticated capability support
  and real authenticated IDLE delivery have therefore **not** been tested here.
  The implementation checks CAPABILITY again after login, before selecting INBOX.
- The read-only Render service inspection confirmed the existing canonical
  `sports-cave-os` service (`srv-d8kl4on7f7vs73dvavv0`), one configured instance,
  and start command `python sports_cave_server.py`. No service was changed.
- The repository starts one Uvicorn application, with no explicit worker count.
  The inspection did not enumerate live OS processes or Render environment secrets.
  Coordination does not assume that rolling deployments or future replicas cannot
  overlap: a database lease elects the only IMAP watcher owner.
- Python 3.12 is used by the deployment. The pinned `IMAPClient==3.0.1` dependency
  provides the established IDLE/DONE/check API; Python's native imaplib IDLE API
  was added in Python 3.14. See [IMAPClient API](https://imapclient.readthedocs.io/en/3.0.1/api.html)
  and [Python imaplib](https://docs.python.org/3/library/imaplib.html).

## Architecture and connection ownership

```text
Existing ASGI server lifespan
  → database lease for the shared mailbox
  → one verified-TLS, read-only-INBOX IDLE connection
  → STATUS-only mailbox signal
  → process-local signal hub
  → authenticated same-origin SSE to the existing top bar
  → existing Email fragment's delta loader + badge + notification loader
```

The watcher starts explicitly after ASGI startup completes, not during module
import, Streamlit reruns, navigation, or browser subscription. Shutdown requests
stop and join it. Repeated starts on the same lifecycle object are idempotent.

The existing private `app_sync_state` table holds two small namespaced entries:

- Lease: owner UUID and database-clock expiry.
- Signal: mailbox, version UUID, UIDVALIDITY, UIDNEXT, UNSEEN, MESSAGES, checked_at.

There is no new table or migration. A conditional atomic claim gives one owner a
60-second lease. It renews every 15 seconds; a 35-second local deadline causes
early shutdown if ownership cannot be refreshed. Signal publication checks and
locks the valid lease in the same short transaction. An expired owner cannot
renew or publish. Transactions set a two-second statement timeout and use the
existing eight-second database connection timeout. This works without session
advisory locks and is compatible with transaction pooling.

If another process exists, it relays the shared signal once per second and retries
leadership every 15 seconds; it does not open IMAP while the lease is held. The
current single instance needs no follower reads. Leader renewal costs about 240
short database transactions/hour. There is no database work per SSE subscriber.

There is **one intended active watcher socket** per mailbox. Existing foreground
IMAP commands still use their separate bounded connections; they never borrow the
watcher socket. The current per-process ordinary-operation limit remains two,
so one watcher plus two ordinary operations is a ceiling of three in this process.
The fixture peaked at two total. The lease fences publication under process
pauses; no distributed lease can forcibly close a paused process's orphaned TCP
socket until that process resumes or its connection dies. On resumption the
expired owner closes before further mailbox work/publication.

## IDLE, reconnect and fallback

1. Connect with verified SSL, authenticate with the existing configuration, check
   capabilities and select INBOX read-only.
2. Read `STATUS INBOX (UIDVALIDITY UIDNEXT UNSEEN MESSAGES)` and publish a baseline.
3. Enter IDLE. Blocking one-second `idle_check` waits do not send IMAP commands.
4. EXISTS, EXPUNGE, FETCH/flag and RECENT responses end IDLE with DONE. Read STATUS,
   publish a new version, then re-enter IDLE. The watcher never requests headers,
   message bodies or attachments.
5. Renew an otherwise quiet IDLE cycle after 20 minutes using DONE, NOOP, STATUS,
   and IDLE. A flag event publishes a new version even if counts are unchanged.
6. Close the transport in `finally` on success, shutdown, failed login, BYE,
   timeout, disconnect, protocol failure, or lease loss. Reconnect delays are
   15, 30, 60, then 120 seconds maximum; a healthy minute resets the failure count.
7. A non-IDLE server closes this probe and leaves existing polling operational;
   capability is probed again after an hour. Coordination failures also leave
   ordinary mailbox browsing/polling operational.

The existing approximately 60-second consolidated STATUS/flags fallback remains
unchanged (30-second shell heartbeat with a 55-second guard). It also runs while
IDLE is healthy, as requested, to catch missed events and non-INBOX changes.
Its existing connection limits, backoff and foreground priority are preserved.

Watcher disconnection does not clear any folders, messages or opened body. It
does not add a new UI status design; existing fallback failure/recovery status
continues to label stale views. Thus a watcher-only disconnection can remain
invisible while successful fallback polling keeps the mailbox current.

## Browser delivery and mailbox updates

The new `/api/os/top-bar/email-events` SSE endpoint uses the existing Bearer token
and Email route permission. Tokens are sent in headers, never URLs. It streams
only the seven allowed signal fields, disables response caching/proxy buffering,
sends keepalive comments, and rotates streams after 55 seconds to revalidate
authentication. Browser reconnect is bounded; destruction aborts the stream.

One SSE stream per existing top-bar instance serves all Email consumers in that
browser. These are HTTP subscriptions, **not additional IMAP watchers**. The
backend reads an in-memory hub at 250 ms intervals. Followers, if any, relay the
database signal into their own hub for their browsers.

Each version invalidates the existing shared transient runtime once and seeds
the actual STATUS result, avoiding another STATUS request for each consumer.
The top bar updates its established badge and calls the established durable
notification loader. The Email component passes the version to its existing
fragment event path; Python validates the version against the server's hub before
bypassing the polling TTL. An arbitrary browser version cannot force IMAP work.

The current delta loader fetches only missing new headers and current visible
flags/membership. It does not fetch bodies, attachments, historical thread bodies,
Shopify data or order data. Four identical session snapshots reuse one header
delta in the process cache. The notification loader still fetches its own small
sender/subject header set; this task does not merge those established code paths.

Busy actions, menus and hidden tabs defer/coalesce signals. A deferred signal
resumes after the action/menu closes or the tab becomes visible. Up to three
1.5-second retries handle an unacknowledged/coalesced version, after which the
unchanged periodic fallback remains available. Selection, search, current folder,
scroll and unsent composer state stay on the existing preservation path. Only
the Email fragment updates; there is no full-app reload for a mailbox event.

## Notifications, data and preserved behaviour

The watcher creates no bell events. Existing durable mailbox/UIDVALIDITY/UID cursor
logic creates them and retains its first-run baseline. Repeated IDLE signals,
fallback checks and app restart do not reannounce old messages. Messages arriving
during downtime remain subject to the existing durable cursor semantics.

Nathan, Maria and extra tabs consume the same real mailbox state. Existing real
IMAP automatic Seen, Mark Unread, flags, move/copy and folder actions are unchanged.
External client changes converge through IDLE plus the retained polling path.

**VentraIP remains the email source of truth.** No body, HTML, attachment, draft,
Sent copy or subject history is accepted by the new coordination store. Bodies
remain in the existing bounded transient display caches only. The new persistent
data is strictly coordination metadata; no logo/content storage was added.

No Email HTML templates, CSS, dimensions, colours, labels, controls, signature
content, MIME construction, SMTP, recipients, attachments, draft persistence,
send progress, Sent verification, context menu design or search logic changed.
Files, Orders and unrelated OS pages were not modified. Top-bar changes are
limited to the invisible Email event transport/configuration.

## Measured results

All timing and load results below are local fabricated-wire results, not VentraIP
production latency or server-resource guarantees.

| One-hour scenario | Result |
| --- | ---: |
| Quiet watcher connections / peak / leaked | 1 / 1 / 0 |
| Quiet watcher IDLE cycles / STATUS / NOOP | 3 / 3 / 2 |
| Quiet watcher BODY or header fetches | 0 |
| Quiet virtual-hour CPU time | 0.016 s |
| Incremental traced allocation during that fake loop | about 7 KB |
| Five arrivals + disconnect: logical watchers | 1 |
| Watcher connections / reconnects / peak | 2 / 1 / 1 |
| Watcher STATUS / signals | 7 / 7 |
| Four sessions + fallback: all connection starts / closes | 132 / 132 |
| Four sessions: peak simultaneous total connections | 2 |
| Four sessions: total STATUS commands | 66 |
| New-message header fetches | 10: 5 UI + 5 notification header sets |
| Watcher or background body/attachment fetches | 0 |
| Notifications / duplicates / leaked connections | 5 / 0 / 0 |

Quiet command counts additionally include connection/login/capability/read-only
selection and final shutdown. Real library connection setup can also issue an
initial CAPABILITY. Renewal has no per-second network command. The fake-loop
allocation excludes prebuilt objects, Python/Streamlit, TLS and library overhead;
it is not the total deployed watcher memory footprint.

Browser arrival-to-visible samples were **3.18 s, 4.32 s after recovery, and 3.19 s**.
These include the Streamlit fixture's arrival button and browser automation
overhead. They demonstrate automatic delivery without Refresh, but do not establish
a production 1–3 second guarantee. Render proxy streaming and authenticated
VentraIP event latency still require the approved deployment smoke test.

The earlier Email rendering performance check still reports zero reading-pane
replacements across 1,000 unchanged models and one replacement per selection.

## Tests and browser verification

- **247 targeted Python tests passed**: IDLE, connection recovery, Email V1/V2,
  performance, signatures, send UX, live actions and notifications.
- Full-suite checkpoint: **3,287 tests**, 131 failures, 36 errors, 36 skipped.
  All 167 failing test identities match the pre-existing performance-pass baseline;
  there are no new failing identities. Two additional SSL/cleanup tests were then
  added and passed in the final targeted run. The full repository suite is not green.
- Actual lease SQL passed local PostgreSQL/PGlite checks for competing claims,
  valid/expired/wrong-owner renewal, fencing, publication, release and takeover.
- JavaScript tests passed for IDLE signal coalescing/retries, existing live menus,
  connection status, notification transport, send status, Email component,
  composer/search focus (2,404 assertions), and app search. Render benchmark passed.
- Python compilation, component JS and top-bar inline JS syntax, `git diff --check`
  and `scripts/validate_render_topology.py` passed.

Browser verification used the real Email component/top bar in the existing local
fabricated shell at **1440×900 and 1920×1080**:

- New messages appeared without Refresh; Inbox and sidebar unread badges updated;
  the existing bell showed the new-email event alongside the existing order event.
- Nathan's unsent reply survived arrivals, a fabricated outage, recovery and a
  subsequent arrival; the selected message stayed selected/visible.
- Maria's separate new-mail text and automatic Maria signature survived shared
  arrivals. Nathan's other tab received the same mailbox update independently.
- Opening a new unread message retained the existing automatic Mark Read action.
- Simulated Thunderbird Seen/Flagged changes reduced unread 4→3 and displayed a
  star while Maria's unsent text stayed intact.
- No layout/template/style changes were required. The fixture's sidebar controls
  are test controls, not additions to production UI.

Screenshots: `output/email-idle-1920.png`, `output/email-idle-maria-1920.png`.
Logs: `output/email-idle-final-tests.txt`, `output/email-idle-full-suite.txt`,
`output/email-idle-load.txt`. Output artifacts are intentionally untracked.

Repeat locally (no real credentials needed):

```powershell
.venv/Scripts/python.exe -m unittest tests.test_support_email_idle tests.test_email_poll_recovery tests.test_support_email tests.test_support_email_v2 tests.test_support_email_performance tests.test_support_email_signatures tests.test_email_send_ux tests.test_support_email_live tests.test_email_connection_recovery tests.test_support_email_notifications
.venv/Scripts/python.exe -m tests.test_support_email_idle
node tests/test_email_idle_component.cjs
node tests/test_email_live_component.cjs
node tests/profile_email_render.cjs
# Optional real-SQL local harness; no cloud database:
npm install --prefix output/email-idle-pg --no-audit --no-fund @electric-sql/pglite@0.5.8
node tests/email_idle_postgres.mjs
.venv/Scripts/python.exe tests/fixtures/email_notifications_preview.py --serve
# Open http://127.0.0.1:8504/?page=email and ?page=email&account=staff
```

## Files and checkout provenance

Production changes:

- `support_email_idle.py` — lifecycle, IDLE loop, in-memory hub.
- `support_email_idle_store.py` — existing-table lease and metadata signal.
- `support_email_events.py` — authenticated SSE endpoint.
- `sports_cave_server.py` — lifecycle and route registration.
- `requirements.txt` — pinned IMAPClient dependency.
- `top_bar.py` — event endpoint configuration.
- `components/sports_cave_top_bar/index.html` — invisible SSE subscriber.
- `support_email_workspace.py` — validated version-triggered delta update.
- `components/support_email/mail.js` — queued/versioned push handling only.

Validation/documentation changes:

- `tests/test_support_email_idle.py`
- `tests/test_email_idle_component.cjs`
- `tests/email_idle_postgres.mjs`
- `tests/fixtures/email_idle_runtime.py`
- `tests/fixtures/email_notification_runtime.py`
- `tests/fixtures/email_notifications_preview.py`
- `tests/test_email_live_component.cjs`
- `tests/profile_email_render.cjs`
- `docs/EMAIL_V23_IDLE.md`

The notification fixture files and live-component test already contained local
recovery edits when this task began; those were preserved. The pre-existing
untracked `tests/test_email_poll_recovery.py` was run but not authored/changed by
this task. No concurrent HEAD change was observed during this task.

## Approval and rollout boundary

Ready for review and an **approved controlled deployment**, with the production
checks below outstanding. It is not claimed to have been validated against an
authenticated real mailbox or Render's deployed SSE proxy.

No new Render service, worker, replica, start command, environment variable,
mailbox credential, Supabase migration or VentraIP setting is required. The
existing server process gains an explicitly owned watcher thread and a dependency
installed by the normal build. Existing database access to `app_sync_state` is
used; if unavailable, the watcher backs off and existing polling remains available.

After approval/deployment, check the safe `email_idle_connected supported=true`
log, live arrival/badge/bell delivery in Nathan and Maria tabs, no duplicate
notifications after a fallback interval, and continuity across a service restart.
Confirm failures log only exception type/delay and normal browsing keeps working.
If post-login IDLE is not offered, the retained polling fallback applies without
mailbox changes. No production action was taken as part of this implementation.
