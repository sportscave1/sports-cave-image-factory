# Email operations and recovery

Phase 4, 25 November 2026. The owner explicitly authorized finalizing Phase 4 and
releasing Phases 2–4 to Git/Render. This supersedes the earlier local-only release
status in the Phase 2 and 3 reports; it does not change their historical results.

## Automatic operation

The certificate worker keeps its durable UID cursor and original send intent
across disconnects, process restarts and deploy overlap. It still handles one
message per bounded read-only session. A successful pass with more pending mail
now schedules a five-second catch-up; otherwise it checks every thirty seconds.
Shared mailbox admission/backoff still applies. Busy admission does not count as
a network failure. A refused connection cannot be forced through by this cadence.

Header-only polls include IMAP INTERNALDATE. Each successful cursor update saves
the visible pending count, whether the bounded UID window has more data, the
oldest pending server arrival date and the start of an observed backlog. No
message text, sender, subject or new UID copy is stored in those measurements.
The count covers the bounded window, not an exact total across the whole mailbox.
Before a failed initial poll, arrival age can be unknown; stale-poll monitoring
remains active. Missing dates use the observed backlog start as a lower bound.

The running worker performs a DB-only health check at most once per minute.
`email_operations_health` logs contain a state and fixed alert codes on state
change, then at most once per five minutes while unchanged. Monitoring errors
produce a safe category-only warning; they never halt recovery, advance cursors,
resend an email or change automation settings. No new service, queue, schema,
public endpoint or external alert subscription is created.

Administrators can open **Email settings → Mailbox diagnostics** for the report.
It includes poll age, queue age, uncertain outcomes, Sent-copy lag, recent
connection failures, server queue/IMAP timings and anonymous browser selection
p50/p95. Samples are bounded to 200 per series and process measurements reset on
restart. Browser timing aggregates are collected locally, sent only on an explicit
diagnostics request and validated again by the server. They are diagnostic
measurements, not authoritative delivery proof. The panel shows its snapshot time;
refresh diagnostics for current values. Ordinary Email users cannot request the
private operational report.

The settings view now repaints when a diagnostics response arrives; the open
customer message does not repaint because diagnostics changed. Browser checks
verified healthy and attention feedback, collected cold timing samples and a
375 CSS-pixel layout without horizontal overflow, using synthetic data only.
No production mailbox, credential or customer record was used in development.

## Thresholds

| Signal | Warning | Critical / action |
| --- | --- | --- |
| Last successful certificate poll | — | More than 120 s while enabled; initial startup has a 120 s grace period |
| Oldest pending arrival / observed backlog | More than 120 s | More than 300 s |
| Oldest queued/in-progress outgoing reply | More than 120 s | More than 600 s |
| Uncertain SMTP outcome | Any | Reconcile the original intent; never resend blindly |
| Accepted reply lacking its Sent copy | More than 300 s | Repair/reconcile its copy; never send the accepted reply again |
| Connection failures | At least 3 in the last 5 min | Identify network, authentication or TLS stage |

The 99.9% monthly availability and healthy-provider 60-second eligibility-to-queue
goals from the four-phase plan remain service objectives, not measured guarantees.
Current cold/warm latency distributions require actual usage samples; synthetic
80 ms acknowledgements are not live provider latency measurements.

## Outage response

1. Verify canonical service `sports-cave-os` (`srv-d8kl4on7f7vs73dvavv0`), live
   commit and `/_stcore/health`. Do not create another primary or change the
   Blueprint to recover an inbox.
2. Inspect `email_operations_health`, `certificate_reply_worker`,
   `certificate_reply_check`, `email_imap_check_failure` and inbox sync logs.
   Stage `dns`/`tcp` before authentication points toward hosting/provider routing.
   Authentication/configuration/TLS issues need the owner to correct the existing
   connection; never disable certificate validation.
3. Keep the durable cursor, pending request and operation IDs. Do not reset the
   mailbox, disable/re-enable the automation to replay mail, delete the outbox,
   or repeat an uncertain send. Let bounded recovery resume when access returns.
4. If HTTP is healthy but mailbox TCP access repeatedly fails, escalate to Render
   and the mailbox provider with timestamps, region, transport stage and safe
   error code. Exclude passwords, bodies, recipients and provider response text.
   Compare other running instances/deploy logs before blaming credentials.
5. A redeploy of the same tested build may move a bad hosting route, as observed
   during Phase 1. Verify the new instance actually authenticates and completes a
   poll; a successful build alone proves neither. Repeated restarts are not a fix
   for a provider outage. Require production-action authorization outside an
   already authorized release/incident task.
6. Failover options are a provider-supported alternate endpoint with verified
   TLS, an approved hosting-region change, or a carefully migrated mailbox.
   None has been configured or live-tested by this release. Verify provider
   support and credentials, preserve mailbox identity/UIDVALIDITY handling and
   durable send records, and run offline plus authorized live checks before
   switching. A mailbox change must not replay old incoming mail.

## Release and verification

Use the existing `main` auto-deploy. Run `scripts/check_orders_release.py` with
disposable local PGlite against the exact committed candidate and retain its
email, Orders/Python, Node and topology results. Push only reviewed task files;
preserve other worktrees. There is no Blueprint sync or migration in this change.

Wait for the matching deploy to become live, verify HTTP and recent successful
certificate polls/health logs, then confirm the existing automation is enabled
and prior accepted replies remain accepted without increased send attempts.
Use read-only queries/logs for this verification. Do not send a second customer
reply as a smoke test. Record the commit, deploy ID, CI outcomes and read-only
verification in the task release evidence outside customer data.

Offline fault coverage includes drop after queue-before-cursor-save, restart
with a fresh durable registry, overlap during inspection, 13 sustained arrivals,
shutdown/connection-reuse fences, bounded catch-up, stalled monitoring and
untrusted diagnostics aggregates. It does not simulate a live provider outage
or claim that upstream failures cannot occur.
