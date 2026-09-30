# Inbox connection and loading verification — 30 September 2026

## Production diagnosis

Read-only logs from the canonical `sports-cave-os` Render service, inspected with
Nathan's workspace approval, show repeated IPv4 TCP timeouts around 8,007–8,063 ms
before TLS/authentication, followed by immediate IPv6 `ENETUNREACH` (errno 101).
Observed window: 05:17–06:02 UTC. The final IPv6 error previously masked the
earlier IPv4 timeout. Provider: VentraIP, IMAP over verified TLS, port 993.

A TCP/TLS-only probe from the local machine succeeded: TCP 83 ms, verified TLS
178 ms cumulative, IMAP greeting received. No login or message operation ran.
This isolates a Render-to-mailbox connectivity problem; it does not establish
which firewall/network is dropping packets. Local mailbox credentials are absent.
Do not call the production connection fixed until a read-only check succeeds
from the actual Render runtime.

## Local reliability changes

- Preserve fresh, operation-owned IMAP sockets and existing concurrency limits.
  Share a total TCP connection deadline across resolved addresses; preserve the
  timeout category; bound socket logout cleanup to one second.
- Serve latest 50 Inbox headers from a process read model and private persisted
  snapshot. Remote mail remains authoritative. No bodies/attachments/passwords
  are persisted in that snapshot. Initial lists already avoided full bodies;
  the previous blocking folder discovery/list path was the latency problem.
- Publish headers before optional folder discovery. Skip six optional folder
  counts on the startup path. No Shopify/customer lookup runs per list row.
- Read bodies asynchronously with coalesced requests and bounded queue/cache.
  Existing compose/download actions await the same read with a bounded wait.
  Sending/mutation paths remain delegated to existing helpers.
- Keep the existing UID/UIDVALIDITY delta mechanism, bounded loaded-message flag
  checks, and normal live notification cadence. The metadata worker reconciles
  about once a minute independently of the page; it does not scan history.
- Keep cached rows/bodies during transient failure, with one compact status.
  Retry transient failures with exponential backoff (worker 15–300 seconds);
  authentication/configuration/TLS failures back off 15 minutes. UI recovery
  no longer stops permanently after two transient failures.
- Retain selected conversation on refresh. Guard delayed body responses by the
  active message identity. Only an explicit existing Open action can mark read.
- Safe stage timings and health fields record category, attempts, last success,
  duration and processed-header count without credentials or message content.

## Measurements and validation

Offline fixture fixes folder/header/body latency at 200/500/800 ms respectively:

| Measurement | Before | After |
|---|---:|---:|
| List path / cached list render | 702.90 ms | 2.16 ms |
| Selected-body request returns to UI | 800.52 ms | 0.41 ms |

These compare blocking work against cached/asynchronous work, not provider speed.
An uncached body still takes its real fetch duration plus the approximately
one-second UI completion check. Zero list body downloads, attachment downloads
or customer/order queries; first page contains 50 rows.

Commands:

```
.venv/Scripts/python -m tests.profile_email_inbox_reliability
node tests/email_inbox_snapshot_postgres.mjs
```

Email/support-email Python suite: 388 tests, 3 skipped. Ten email JavaScript
test files pass. Changed Python compilation, JavaScript syntax and
`git diff --check` pass. Isolated PostgreSQL validates the actual migration and
queries: repeatable migration, timestamp fencing, scope isolation, RLS and
denied anon/authenticated reads.

Browser fixture tested at 1920×1080, 1440×900 and 1280×900: list retained on
outage, selected cached body retained, single reconnect status, automatic recovery,
thread switching and manual refresh selection preservation. No browser console
errors observed. This was the real Email component in an offline Streamlit
fixture, not authenticated production or the entire OS shell.

## Files involved

Runtime: `support_email_reads.py`, `support_email_snapshot.py`,
`support_email_idle.py`, `support_email_provider.py`, `support_email_transport.py`,
`support_email_workspace.py`, `components/support_email/mail.js`.

Database: `migrations/20260930055619_support_email_inbox_snapshot.sql`.

Validation: `tests/test_email_inbox_reliability.py`,
`tests/test_email_permanent_reliability.py`, `tests/test_email_reconnect_lifecycle.py`,
`tests/test_email_connection_status.cjs`, `tests/test_email_reader_component.cjs`,
`tests/email_inbox_snapshot_postgres.mjs`, `tests/profile_email_inbox_reliability.py`,
`tests/fixtures/email_inbox_reliability_preview.py`.

## Release gates / limitations

1. Apply the private snapshot migration through the normal approved migration
   process. It was tested locally, not applied to production by this task.
2. Run `python scripts/check_support_email_health.py` in the actual Render service
   environment. It uses verified TLS, read-only EXAMINE/STATUS and emits safe stage
   timings. If TCP still times out, investigate Render outbound reachability and
   VentraIP firewall/allowlisting with the hosting providers. Do not disable TLS
   verification, force guessed IPs, or change credentials as a workaround.
3. Verify login, list, opened bodies and automatic sync read-only after the route
   works. No authenticated live mailbox verification was possible locally.

A new snapshot cannot display mail that has never synced successfully. Previously
opened bodies survive a transient outage in the session cache; they are not
persisted across restarts. DNS resolution remains subject to OS resolver timing.
The new worker coalesces per process; existing provider/runtime coordination
prevents foreground/background socket overlap. No full mailbox replica or broad
history sync was added.

No live email was sent, moved, archived, deleted or marked read/unread. No deployment
or git commit/push was performed by this task. Deployment readiness remains
conditional on the migration and Render network verification above.
