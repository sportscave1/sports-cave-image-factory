# Inbox connection recovery — 28 September 2026

## Proven live failure and remaining network issue

Read-only application logs were inspected in Nathan's approved Render workspace,
for the existing primary service `sports-cave-os` (`srv-d8kl4on7f7vs73dvavv0`).
Around the screenshot time (22:53 Sydney / 12:53 UTC), connection attempts failed
**before authentication**, not while reusing an old selected IMAP connection:

```text
12:48:34 UTC email_imap_transport_failure stage=tcp family=ipv4 type=TimeoutError duration_ms=8007
12:48:34 UTC email_imap_transport_failure stage=tcp family=ipv6 type=OSError errno=101
12:51:42 UTC email_imap_check_failure stage=tcp code=network type=OSError errno=101 duration_ms=8105
12:53:56 UTC email_imap_check_failure stage=tcp code=network type=OSError errno=101 duration_ms=8066
```

IPv4 TCP timed out; IPv6 had no route (`ENETUNREACH`). The adapter reports the last
resolved-address failure; the existing transport logs preserve both attempts.
The same failures affected the isolated IDLE watcher. These logs do not prove
whether the external cause is mail-server filtering, a firewall or network routing.
No production setting, server, credential or provider was changed.

**This local fix hardens recovery. It cannot make an unreachable mail server
reachable, and production connectivity is not claimed to be permanently fixed.**
If this pattern continues, verify TCP/TLS reachability from the current Render
instance to the configured IMAP host/993, and check provider firewall/connection
logs for that source. The repository already provides
`scripts/check_support_email_health.py` for an explicitly approved operational
read-only check; it was not run against the live mailbox during this task.

## Why the error could persist

`Connection interrupted. Reconnecting automatically.` is the safe `deferred`
message emitted by the shared admission/backoff gate after a previous failure.
It is not evidence of a cached socket. A cold workspace has no successful snapshot
to display, hence `Mailbox unavailable`; a failed new-folder load must also hide
the previous folder's rows.

The existing page relied on heartbeat retries without a terminal Retry state.
Body reads lacked the provider's existing read-retry wrapper; their errors lost
classification at the controller boundary. A returned IMAP `BYE` was not retryable,
although an `imaplib.abort` exception was. Authentication failure could subsequently
be obscured by a generic backoff message. These application recovery gaps are fixed.

## Connection ownership, health and timeouts

The provider stores configuration/a connection factory, **not a persistent socket**.
Every uncached wire operation opens, authenticates, selects its requested folder
read-only, verifies UIDVALIDITY when applicable, and releases the socket in `finally`.
No `st.cache_resource`, global or session-state IMAP socket is handed to the UI.
Consequently no redundant foreground NOOP health check was added. A closed socket
is discarded; the retry uses a new authenticated connection and reselects the folder.

The existing dedicated IDLE watcher has its own lease/connection and NOOP/STATUS
renewal checks. It never lends a socket to the page. Existing foreground admission
serialization and background connection budgets remain. Existing eight-second
socket/connect/read timeout and verified TLS/address fallback remain unchanged.
Data/display caches remain socket-free, so normal UI reruns do not add logins.

## Recovery policy

1. Existing safe read wrapper: one immediate fresh-connection retry for recognized
   transient failures. Added to body, mailbox-draft and attachment reads; folder/list
   reads already used it. Returned BYE now follows the abort retry path.
2. If a workspace read still fails, retain the last successful same-folder view.
   Keep its selected conversation, cached bodies, folder mapping and compose state.
3. The component schedules at most **two delayed workspace recovery attempts**.
   Delays start at 15/30 seconds and respect shared admission backoff (up to 120s).
   The workspace revalidates the deadline; duplicate/rerendered events cannot force
   extra reads. Each cycle still uses the provider's bounded read policy.
4. Recovery refreshes header membership and any failed folder discovery, then loads
   the selected missing body. Existing valid selection survives; invalid Inbox
   selection falls back to the existing first/newest rule. Empty Inbox stays empty.
5. Success clears recovery/error/live-error state and only its connection notice.
6. Exhaustion shows `Mailbox connection unavailable.` and **Retry**. Foreground
   heartbeat/push retries stop. Retry/explicit Refresh starts a new bounded cycle
   with fresh connections. Authentication/configuration/TLS/folder-selection errors
   stop automatically and retain their specific diagnostic.

Background notification/IDLE workers retain their existing separate bounded-rate
polling/lease behavior; they are not new UI retry owners. No new background job was
added. Cold-page renders cannot bypass the recovery attempt counter. Changing
folders during backoff cannot display Inbox data under an Archive heading.

During an active recovery request a small spinner and `Reconnecting mailbox…`
appear in the existing status line. The OS shell, mailbox layout and safe cached
content remain. Waiting/stopped states do not pretend that the connection is live.
No overall layout, folders, compose or reading-pane design was changed.

## Mutation safety, caches and logs

SMTP send, flags, move/copy, archive/trash/junk, targeted Trash deletion and Sent
append are **not** wrapped in automatic read retry. Existing operation IDs,
confirmation and uncertain-outcome handling remain. Recovery invokes only reads,
does not mark messages read and never replays a previous UI mutation.

Folder metadata TTL, opened-body identity/cache, MIME parsing and selected-message
lazy loading remain. Recovery invalidates header snapshots/failed discovery, not
all cached mail. UIDVALIDITY still invalidates old bodies. Explicit mutations retain
their existing invalidation rules. No normal-refresh speculative body fetch was added.

Structured events now include connection-opened (debug), read reconnect-started /
succeeded, operation-failed (code/attempt count), workspace reconnect-started /
failed / succeeded. Existing transport logs retain stage/family/error type/errno.
No passwords, tokens, bodies, addresses or raw provider exception text are logged
by the new events. Authentication classification survives shared backoff.

## Changed files for this task

- `support_email_provider.py`: safe read retry coverage, BYE handling, safe metadata/logs.
- `support_email_runtime.py`: expose safe backoff/classification metadata.
- `support_email_logic.py`: preserve safe failure metadata through display reads.
- `support_email_workspace.py`: bounded recovery, correct selection/body restoration,
  state cleanup, same-folder cache protection and manual Retry.
- `support_email_page.py`: cold reruns respect the controller retry owner.
- `components/support_email/mail.js`: recovery feedback/timer/Retry integration.
- `components/support_email/style.css`: tiny status-line spinner/Retry styling only.
- `tests/test_email_reconnect_lifecycle.py`: seventeen new wire/controller/page tests.
- `tests/test_email_reconnect_component.cjs`: actual feedback/timer logic tests.
- `tests/email_reconnect_preview_app.py`: isolated fault-injection browser harness.
- This report and `docs/email-reconnect-evidence/` screenshots.

Earlier uncommitted performance work remains in the checkout. Campaign/Automation
files were not modified by this task; their earlier changes were preserved.

## Verification

- Email suite: 126 tests run; 125 passed, one SQL-dependent navigation check
  skipped in this run and passed in the separate configured navigation run.
- Support Email suite: 212 passed.
- Startup, Email navigation and navigation-performance suites, in isolated test
  processes: 6 + 6 + 23 passed. Isolation avoids these suites' Streamlit mock-state
  interference when combined in one process.
- Seventeen focused reconnect tests pass (included above), plus a 72-test final
  targeted regression run for reconnect, selection/cache, live checks and provider.
- Nine JavaScript/component scripts passed, including new reconnect timer/feedback
  tests, existing send status, Trash deletion, live/IDLE, notification and focus tests.
- Seven changed Python files compiled; `git diff --check` passed. The Windows
  line-ending notices are informational and did not fail the check.

All network failures are fabricated. Tests cover abort/BYE, timeout, EOF/reset,
broken pipe, fresh reselect, bounded failure, authentication, cold load, selected
body, valid/invalid selection, empty Inbox, folder change, manual Retry, repeated
events and mutation non-replay. Existing send/Sent-copy/Trash safety suites remain.

Browser checks use the actual app shell/Email component with fake mailbox data;
SMTP, production IMAP, database and external HTTP requests are blocked. At
1366×768, 1440×900 and 1920×1080, exercised cold Inbox recovery, selected-message
failure, persistent Refresh outage, terminal Retry and successful restoration,
folder-selection interruption and return to Inbox. The retained selected message
and status transition were verified without a browser refresh.

Local verification command: `python tests/email_reconnect_preview_app.py --serve`.
The module docstring describes how to arm only fake provider faults.

No live email sent/deleted, no automation activated, no marketing enabled, no
production database write, commit, push or deployment. Safe for Nathan to test
locally. Live TCP connectivity still requires operational verification separately.
