# Inbox and sidebar notification reliability

Implemented locally on 8 October 2026. No deployment, production mailbox reads/writes or customer sends. Existing local automation-publication and Social Media badge changes were preserved.

## Diagnosed causes

- Email counts were discarded after 120 seconds, both in the server cache and sidebar code. A temporary provider failure therefore removed a real unread badge. Concurrent refreshes returned no count.
- The email status HTTP request waited for IMAP status/cursor processing. This was already header-only, but network latency still delayed the response.
- Orders refreshed the cache timestamp by replacing its payload with an empty object before fetching. A failed request then lost the count across reloads. Failure of both backend sources defaulted to zero.
- Wall badge heartbeat loaded the notification centre's activity sources and notification rows even when the bell was closed.
- Failed asynchronous message reads stayed cached for the normal 20-second TTL, replaying the same exception after recovery. A skipped provider backoff was treated as another sync failure. Restoring a recent peer-worker snapshot restored data but not connection health.
- Normal pending mailbox reads could display “Reconnecting” while their retry was running.
- Automatic browser send-confirmation checks could perform IMAP reconciliation alongside the durable outbox worker. Browser counters did not reflect the worker's persisted six-attempt limit, so refresh could prolong the confirming presentation.

These are verified code paths and fixture reproductions, not a diagnosis of current production provider/network health. No live credentials or email contents were inspected.

## Changes

The existing email status endpoint now returns the credential-scoped count snapshot immediately and coalesces refresh work on one bounded thread in the existing process. Existing IMAP admission limits, durable arrival cursor and notification deduplication remain. While a refresh is genuinely pending, the sidebar makes at most eight one-second follow-up reads, then uses its existing heartbeat. No new websocket, service or deployment resource was added.

Last known email/Orders/wall counts survive refresh failures. Only confirmed zero clears them. Email stale counts carry a refreshing tooltip; unavailable data does not become zero. Session cache identity now also includes the configured mailbox identity/credential fingerprint in its existing hashed revision, in addition to user, role and session scope. No message bodies or secrets are persisted in browser storage.

Wall heartbeat uses `counts_only=1` on the existing authenticated notifications endpoint. This skips activity-source loading and returns a SQL count using the same permissions, deletion and per-user seen rules. Opening the bell still loads its normal notifications. Social Media and Email badges stay on their parent menus; menu opening does not mark anything read. Orders keeps its existing actionable definition and refresh cadence.

Existing asynchronous inbox reads, in-memory conversation caching, incremental UID sync, lazy bodies, stable selection, autosave and submitted search are retained. Failed read results are released for a new attempt; the provider circuit breaker still governs connection retries. Deferred background work does not invent a new connection failure. Recent confirmed peer snapshots restore healthy status; snapshots older than the existing health limit cannot claim Connected. Normal pending work is labelled Syncing.

Automatic confirmation now reads the durable receipt instead of repeating IMAP reconciliation. Receipt metadata includes persisted reconciliation attempts and creation time, without MIME or attachments. After six worker attempts or 15 minutes with an unknown outcome, the UI stops its automatic-confirmation spinner and offers the existing explicit check. The outcome remains **unknown**, the draft stays protected, and nothing is resent. The existing durable worker, Message-ID reconciliation and confirmed acceptance rules remain authoritative.

## Measurements and verification

All timings are local fixtures, not production guarantees.

| Check | Before | After |
|---|---|---|
| Count response with simulated 500ms provider latency | 500.35ms blocking | 0.74ms returning cached count; refresh continues |
| Concurrent count refresh submissions | Empty response during active poll | Ten calls share one refresh and retain known count |
| Failed read after provider recovery | Exception retained until 20s TTL | Next request can retry, subject to provider backoff |
| Wall heartbeat activity loading | Activity sources plus notification rows | Zero activity-source reads; count query only |
| Browser automatic unknown-send check | May issue provider reconciliation | Receipt metadata only; worker owns provider checks |

Edge browser verification: first local fixture navigation 2,577ms including Streamlit startup and synthetic provider latency; subsequent warm-process navigation 532ms; visible row selection 25ms. Cached conversations remained visible during simulated outage and recovered to Connected. Desktop and 390px viewport completed without runtime exceptions. No baseline browser comparison is claimed for those timings.

The existing notification microbenchmark before edits recorded 7.741ms mean fixture poll and 0.0022ms cache hit, with zero body/attachment fetches. These existing strengths were preserved. The older inbox profile compares a synchronous controller with an already-existing async facade, so its large speed difference is **not** attributed to this change.

Regression coverage includes permissions, user isolation, stale counts, confirmed zero, ignored older responses, parent badge placement, deferred reads, cached disconnect/recovery, read/unread, search/selection, autosave, send outcomes, bounded retries, no duplicate sends, existing IDLE and polling ownership. Count SQL was executed against disposable local PGlite. The local SQL adapter is not a production concurrency load test.

The consolidated Python run completed 275 tests: **274 passed, one skipped**. No Python regression failures remained.

Component suites passed for badges, shared heartbeat, IDLE, reconnect, send status, autosave, reader, Trash and HTTP request deduplication. Python compilation and diff checks passed. The old `profile_email_render.cjs` DOM microbenchmark could not run because its adapter lacks current render helpers; no rendering-speed claim is based on it. Browser checks above exercise the actual renderer instead.

## Files

Production:
- `support_email_notifications.py`: immediate/coalesced count refresh and stale preservation.
- `top_bar_api.py`: fast count endpoint, wall count-only path, unavailable Orders count.
- `top_bar.py`: mailbox-scoped browser cache identity.
- `components/sports_cave_top_bar/index.html`: badge retention, startup refresh, bounded pending follow-up, lightweight wall polling.
- `wall_preview_notifications.py`: permission-preserving count-only query.
- `support_email_reads.py`: failed-read recovery and accurate restored/deferred health.
- `support_email_workspace.py`: pending-vs-reconnecting state and receipt-only automatic confirmation.
- `support_email_durable.py`: lightweight persistent verification metadata.
- `components/support_email/mail.js`: accurate pending-read status text.

Tests/profiling:
- `tests/test_email_fast_status.py`
- `tests/profile_email_fast_status.py`
- `tests/email_fast_inbox_browser.cjs`
- `tests/test_support_email_notifications.py`
- `tests/test_email_notification_component.cjs`
- `tests/test_email_live_component.cjs`
- `tests/test_order_action_notifications.py`
- `tests/test_wall_preview_notifications.py`

## Rollout and limits

No migration or dependency added. Existing notification tables and outbox columns are reused. Deploy through the normal application/worker workflow when approved, restarting existing processes to load the new Python modules. No Render topology or plan changes.

Real IMAP/SMTP latency, sustained rate limiting, physical mobile devices and long-running production sessions remain unverified. Fresh counts still depend on provider availability; cached counts are explicitly last known. With no cache and an offline provider, no number can safely be shown. Send acceptance cannot be made certain by a UI timeout: an unresolved delivery remains locked against resend and may require mailbox-administrator verification. Existing search remains submit-driven rather than adding requests on every keystroke. The three-column layout and unrelated CRM/campaign/automation behaviour were not redesigned.
