# Mailbox reliability — local implementation, 26 October 2026

Follow-up release review: see `RELEASE_REVIEW.md` for comparison against live revision `5980a803`, the duplicate acceptance-persistence fix, and final release-plus-task test results (36 SQL/recovery tests). The measurements and production investigation below describe the original implementation session.

Follow-up live runtime diagnostics: see `RUNTIME_NETWORK_DIAGNOSTICS.md`. Actual primary/worker probes on 26 October now succeed through verified TLS and greetings over IPv4; IPv6 resolves but has no route. The historical TCP failure below must not be read as proof of a continuing IPv4 block. Authentication/provider mailbox content and the unknown send remain unverified.

## Status and scope

Implemented and tested locally, uncommitted. Live mailbox remains unpatched until an authorised release. No commits, pushes, merges, deployments, production writes, customer sends, cursor resets, queue clearing or draft deletion were performed. Production investigation used read-only logs and bounded metadata SELECTs; production MIME and credentials were not copied into test fixtures.

Task `20261025-35ed7e58`, owner `codex-mailbox-reliability-01a157b1-20261026`, branch `codex/task/email-mailbox-reliability-sync-recovery-and-unkn-20261025-35ed7e58` has its own Studio worktree. The original EMAIL category checkout (`codex/category/email`) had unfinished work and was preserved. Verified the repository root, branch, Git worktree list from the primary repository, Studio registry and task owner before edits. Task base: `6e2805d058713cc64cfa70e7a85ee23ea66db7e1`; email modules have no differences against the fetched local `origin/main` at `166683874fca7d5332b3d9bd0f6ca366edc8f8dc`. Read-only Render service metadata reported live commit `95b8c223baadf24717483c3fa5d9dbac0384d490`, deploy `dep-dbek865g1s2s73fsb0l0`. This is not a claim to have compared every live deployment file byte-for-byte.

## First failing transition and freshness

The observed failure is **Render → IMAP TCP connection, before authentication**. In the bounded 25 October 18:00–21:39 UTC log window, repeated `email_imap_check_failure stage=tcp code=timeout type=TimeoutError` took approximately 8,042–8,371 ms. Index sync retried about every 300–304 seconds. For example, sync run `67be903b-e298-43bd-894f-9a6995c03352` at 21:39:29 UTC timed out at TCP in approximately 8,107 ms, retry 304 seconds. IDLE reconnect logs also showed connect/protocol failures with increasing delays. Fresh worker leases at 21:44:55 UTC show the background processes were still running; there is no evidence that lazy rendering simply stopped all workers.

The DB snapshot is actually stale, not just an incorrect warning:

- Last provider sync `2026-10-24 23:53:49.486240 UTC` (25 October 10:53:49 Sydney), stored update `23:53:51.717095 UTC`.
- Latest stored received timestamp `2026-10-22 01:58:50 UTC`; latest message date `01:58:39 UTC`.
- UIDVALIDITY `1624495646`, high UID `114`, provider total at that old sync `86`, stored header count `50`.
- The existing 50-header index is bounded by design; older messages use pagination. This count does not prove messages were lost.

Database metadata reads and worker coordination succeeded. Authentication validity after the failure cannot be inferred: TCP never reached authentication. This provider uses IMAP/SMTP credentials and IDLE plus periodic catch-up, not OAuth tokens or expiring webhook subscriptions. Exact current provider Inbox/Sent contents could not be compared because mailbox credentials were unavailable. Consequently, newer provider messages and their visibility delay remain unverified.

An unauthenticated Windows probe to the configured default host `ventraip.email:993` resolved IPv4/IPv6, verified TLS and received an IMAP `* OK` greeting in 7.916 seconds (DNS 1.686 seconds; n=1). It performed no login, mailbox selection or message reads. The current Render host override was not independently verified. Local reachability does not prove Render reachability or identify a firewall/routing owner. Cloud/provider connectivity needs an authorised operational investigation; changing application code cannot repair a blocked TCP path.

## Unknown send — still unresolved, do not resend

Exact operation `11b2a2bc-5643-42cb-9a5b-5930dc10d35e`:

| Persisted metadata | Evidence |
| --- | --- |
| State | `unknown`, copy `pending`, error `NETWORK` |
| Created | 7 October 2026 04:43:07.548302 UTC |
| Last updated | 7 October 04:43:34.938441 UTC |
| Due | 7 October 04:56:02.346278 UTC |
| Submission attempts / reconciliation attempts | 1 / 6 |
| SMTP accepted_at | NULL |
| Exact Message-ID | `<sc.11b2a2bc-5643-42cb-9a5b-5930dc10d35e@sportscaveshop.com>` |
| Sent policy / folder | append / Sent |
| Persisted payload size | 44,271 bytes; payload was not read |

No retained logs were returned for the bounded operation-specific October 7 search. This does not prove submission failed. The original code permanently excluded reconciliation work after six reservations, explaining why this row never received another automatic check. The send predates the October 20 performance release. Neither SMTP acceptance nor recipient delivery is established. No resend or live-row change was made.

A bounded audit since 19 October 13:00 UTC found four accepted operations, all with acceptance timestamps and appended Sent copies, one submission attempt each, no reconciliation attempts. Their creation/update window ended 22 October 01:26:58 UTC. An all-history outstanding aggregate found only the target unknown/pending operation. There are 27 active draft rows across all actors; that is not directly comparable to the screenshot's six actor-scoped drafts. Drafts were preserved.

To resolve the old send requires authorised read-only provider Sent search for the exact Message-ID and/or original provider SMTP submission/queue logs around 7 October 04:43 UTC. A matching Sent copy confirms provider storage, not recipient delivery. No approved sandbox mailbox was available for actual send verification.

## Local repairs

- `support_email_provider.py`: incomplete incremental header FETCH now rechecks whether missing UIDs still exist and raises a retryable error before advancing the cursor. Confirmed expunges remain valid. Complete batches add no extra search. Existing pagination, UIDVALIDITY handling, deduplication, sanitisation and deferred bodies remain.
- `support_email_reads.py`: dead index threads can restart; cached snapshots remain available during errors. Health exposes last attempt/failure, failure stage, retry delay and actionable TCP/auth/TLS diagnosis. Recent shared snapshots cannot hide a newer local failure; a newer confirmed success clears the old failure diagnosis. Last-success time remains tied to successful sync.
- `support_email_idle.py`: dead IDLE watchers can restart without creating duplicate live threads or overriding shutdown. The existing 60-second periodic catch-up remains the missed-event fallback.
- `support_email_durable.py`: first six reconciliation reservations retain the existing short schedule; subsequent checks back off through roughly 15/30/60 minutes with jitter, rather than stopping forever. Queued sends take priority. Unknown/in-progress submissions are never retransmitted. An observed SMTP 250 is retained in a bounded process-local acceptance buffer if DB persistence fails; the worker retries receipt persistence only. Exact Sent confirmation records its source without inventing an SMTP acceptance timestamp. Outbox workers can restart after thread death.
- `support_email_smtp.py`: safe operation UUID and SMTP phase diagnostics, without raw errors, recipients, credentials or body data in logs. Existing protocol and persistent operation claims remain the duplicate-send guard; SMTP provides no submission idempotency key here.
- `components/support_email/mail.js`: existing status text exposes diagnosis and truthful queued/unknown state; no layout changes. Existing reply, drafts, HTML sandbox and lazy body/image/attachment paths remain.

No new infrastructure, dependency, migration or Render configuration was introduced. The acceptance buffer is process-local: process death before a failed DB write is repaired may still lose observed acceptance evidence. The durable claim then remains ambiguous and is reconciled, never blindly resent. Concurrent processes also cannot share that temporary in-memory evidence before persistence recovers.

## Checks

- Broad focused Python run: **296 tests, OK, eight existing SQL-dependent checks skipped**. Includes inbox, read performance, privacy, composer/send UX, lazy conversations, threading, render/sanitisation, Sent lifecycle, trash, roles, drafts/storage, pagination/full conversations, dial backoff, replies, live sync, IDLE and connection recovery.
- Separate disposable local PostgreSQL-compatible PGlite run: **35 tests, all passed**, including 13 new recovery cases and existing durable-send integration cases. This is not a test against a live PostgreSQL server; row-lock/concurrent transaction fidelity remains a limitation of the fixture.
- Faults exercised: credential rejection (this is password auth, not OAuth token expiry), missed IDLE event, duplicate headers, provider Retry-After, TCP interruption, stale snapshot restore, dead thread restart, shutdown guard, partial FETCH, receipt persistence failure after SMTP acceptance, process/registry restart, exhausted reconciliation and queued-send priority. No duplicate SMTP call in the ambiguous/restarted cases.
- Virtual missed-event test runs the real periodic loop with a controlled wait: next 60-second poll exposes one newly available UID exactly once; no body/attachment fetch. This is simulated recovery, not a measured live availability SLA.
- Five component Node suites passed, including 73 scheduler/context/menu assertions and 20 cache/helper assertions, plus connection status, send states and reader sandbox checks.
- Actual component in Chromium against the safe loopback fixture: 12-message conversation loads one body automatically; expanding another brings the total to two, preserves the first iframe, and makes zero attachment/remote requests. Cached mail remains usable while TCP diagnosis and unknown-send state are shown; reply source remains correct. No browser errors. See `browser.json` and `browser.png` (synthetic data only).
- JavaScript syntax and `git diff --check` passed. Test transports were fake, with no mailbox credentials, real delivery or CRM activation.

## Comparable timings

All figures below are **milliseconds, median / p95, n=50 per before/after case**. Before source was saved before editing (see `baseline-source.json`). Provider/controller opening tests are fabricated local fixtures, not browser or live network latency. Cold setup includes mock settings and an initial 50-header load. Send tests use disposable SQL plus fake SMTP/IMAP, with two fixed 2 ms delays. Small differences are consistent with local timing variance; no live speedup is claimed.

| Scenario | Before median / p95 | After median / p95 |
| --- | ---: | ---: |
| Cold mailbox | 40.827 / 44.334 | 40.696 / 42.427 |
| Warm mailbox | 0.340 / 0.378 | 0.332 / 0.355 |
| Cold conversation | 0.610 / 0.696 | 0.601 / 0.662 |
| Warm conversation | 0.048 / 0.064 | 0.047 / 0.055 |
| Manual refresh completion | 1.999 / 2.262 | 1.995 / 2.151 |
| Send click → queued acknowledgement | 16.945 / 53.528 | 14.681 / 43.111 |
| Send click → simulated provider acceptance | 42.315 / 117.558 | 37.129 / 104.433 |
| Send click → simulated Sent visibility | 92.737 / 194.644 | 76.508 / 186.456 |

Call counts per opening/refresh iteration are unchanged: two header calls, one body, zero attachments; all 50 iterations consistent. Raw results: `before-timings.json`, `after-timings.json`. Live cold/warm UI, provider availability → OS visibility, cloud recovery duration, actual acceptance/Sent latency and recipient delivery were not measured. No real sending, provider Inbox/Sent comparison or throttled live-network comparison was possible without the missing approved mailbox access. These limitations do not block the independent local fixes above.

## Files and handoff

Six production files listed above; updated expectations in `tests/test_email_durable_delivery.py`; new `tests/test_mailbox_reliability_recovery.py`, `tests/benchmark_mailbox_reliability.py`, `tests/mailbox_reliability_postgres.mjs`, `tests/mailbox_reliability_browser.cjs`; this evidence folder. Ignored pre-change snapshots and disposable runtime copies remain local for reproduction. Original category work remains untouched.

Implementation status: **locally implemented and tested, with production connectivity and provider end-to-end verification unresolved. Live mailbox remains unpatched until an authorised release.**
