# Campaign Review and Send repair — local release preparation

Task: 20261026-2398b49c. Owner: codex-campaign-send-20261027-01a157b1.
Branch: codex/task/email-campaign-review-and-send-verification-mism-20261026-2398b49c.
Status: owner-approved release 191b118594808fcf6453e7a3d0d84116f41d3f2b is deployed.
Original campaign recovered and SENT at 11:57:02.483 AEDT; all 2,241 eligible original recipients
have unique provider acceptance receipts. The completion-latency follow-up is also deployed to
the existing CRM worker at 356ae9c9e0e1765442318a52eb1a600433a6c28e.
See the live release evidence below for completion status, timings and limitations.

## Exact live failure

Campaign 3f61e092-26ec-57dd-9327-117bdd2ceb77, “All editions | Early Bird Black Friday”,
subject “Collect 2+ editions and save 15%”, Global, reviewed 2,242 recipients, draft version 19.
Review b4e8fb18-f849-40f3-851a-ba3155e86e66 was created at 23:30:22.970998 UTC on October 26.
Operation ab3842b9-2ecf-453b-978c-377bbf7ce5ab was durably accepted at 23:30:42.229402,
then failed at 23:31:08.526756 (26.297 seconds later), attempts=1, settings_changed.

Read-only SQL confirmed one accepted operation, zero crm_campaigns publication rows,
zero recipient jobs, and zero production provider submission records. Repeated clicks did
not produce multiple accepted operations. Five review snapshots were created between
23:28:37.574983 and 23:30:22.970998. No workspace setting changes occurred during the failure window.

Read-only Python in the actual Render worker instance qs4mk compared every saved rendering
setting against CampaignStore.render_settings(). Exactly one differed:

| Field | Saved web review | Worker |
|---|---|---|
| test_unsubscribe_url | https://sports-cave-os-webhooks.onrender.com/crm/unsubscribe/test | empty |

This is a preview-only URL. Production rendering receives validated recipient-specific Shopify
unsubscribe URLs. The old raw dictionary equality wrongly treated this environment difference
as a production rendering change. No unstable hash or changed campaign content was required.
Acceptance creates preparation work, not recipient sends; the worker rejected before publication.
The old terminal-preparation trigger and review boundary then prohibited re-reviewing the same
campaign, which explains the instruction to duplicate even though no recipient had been dispatched.

A separate earlier internal test WAS delivered. Provider ID
01a17a88-50bc-7b18-aece-9d0527e807f5: accepted 23:25:18.063267;
webhook sent 23:25:18.024, delivered 23:25:19.642, opened 23:25:30.198.
Read-only GET /emails/{id} from the worker confirmed last_event=opened. That test is not
the 2,242-recipient broadcast. No new live emails were sent during this repair.

## Changes

- crm_campaign_contract.py: persist actual sender, reply-to and renderer version alongside
  the reviewed configuration. Compare deterministic JSON values, excluding only the proven
  preview-only URL. Retain the exact persisted settings for publication and immutable delivery.
  Genuine settings changes still fail closed, including a second check immediately before publication.
  Legacy snapshots retain their previous sender coverage; new snapshots add explicit sender checks.
- crm_campaign_send.py / crm_campaign_snapshot.py / crm_campaign_preparation.py /
  crm_campaign_reprepare.py: explicit re-review and recovery of failed, unpublished campaigns.
  Recalculate current eligibility but intersect with the original reviewed identities and hashes.
  Keep campaign/content/version unchanged, record old/new operations in history, and require
  explicit send confirmation. Never recover published, partial or uncertain delivery through this path.
- migrations/20261027000251_crm_campaign_safe_recovery.sql: retain terminal locks except for
  transaction-fenced, zero-recipient-work recovery with a new fresh immutable snapshot. Database
  checks preserve content and prohibit added recipients, even if application checks are bypassed.
- components/campaign_recovery/accept_feedback.js and crm_campaign_send_ui.py: immediate
  Submitting acknowledgement, suppress additional clicks, and let React receive the first enabled
  event before disabling the button. Remove rerender-time imperative overrides of React's disabled state.
  Durable uniqueness and lost-response reconciliation remain server-owned.
- crm_campaign_review.py: reuse completed reviews beyond the old 30-second cutoff while
  content/settings/audience identity and validity remain unchanged; maximum four minutes from
  completion and still bounded by the audience job's existing 60-second TTL and DB five-minute TTL.
- crm_campaign_home.py / crm_campaign_progress.py / crm_campaign_progress_ui.py: recovery action
  on the existing page; distinguish unclaimed Queued from leased Verifying. Sending and final
  completion continue to depend on persisted recipient outcomes.
- crm_worker.py: preparation polling cannot wait behind lifecycle audience maintenance; use a
  separate thread in the same existing worker process, retaining database claims and fencing.

Designs, content, catalogue, offers, recipient selection, unsubscribes and dispatch idempotency
were preserved. No new infrastructure, dependencies or production configuration changes.

## Verification and measurements

105 tests passed in 18.563 seconds against a fresh disposable PGlite PostgreSQL fixture:
`python -B -m unittest tests.test_crm_campaign_contract tests.test_crm_campaign_preparation
tests.test_crm_send_flow tests.test_crm_send_progress tests.test_crm_campaign_home tests.test_crm_batch_dispatch`.
Earlier focused fast-review tests also passed. Tests cover genuine and preview-only changes,
explicit recovery, database rejection of added recipients, duplicate acceptance, lost commit
acknowledgement, expired leases/restart, suppression changes, partial batches, provider-accepted
receipt persistence failures, uncertain outcomes, refresh/navigation and truthful final status.
The fixture serializes transactions; this is not proof of competing real PostgreSQL sessions.
An overlapping timing/test run interfered with this shared fixture; the final suite was rerun
alone against a fresh database and passed. No live database tests or production writes occurred.

Real Edge/Streamlit browser checks with fake receipts and loopback-only traffic:

| Condition | Released controls | Fixed controls |
|---|---|---|
| Normal | confirmation control remained disabled; no receipt | click feedback 0.2 ms; main-page status 197.8 ms |
| 250 ms latency, 150 KB/s down, 75 KB/s up | disabled; no receipt | four rapid clicks, one accepted job; feedback 0.1 ms; main-page status 577.5 ms |

`node tests/test_crm_campaign_accept_click.cjs` passed. The baseline reconstructs released
controls in a fabricated fixture; it does not establish the exact timing of the owner's historical
3–4 clicks. The old code's microtask disable and rerender overrides race React's ownership.
`node tests/test_crm_home_send_ux.cjs` also passed: one job, page progresses through
0 / 1,095 → 100 → 500 → Sent, refresh creates no replacement, four viewport widths fit.
Those scripted fake progress intervals are correctness checks, not provider throughput measurements.

Final review also separated the old FAILED receipt from acceptance of a new recovery operation.
After that change, the focused contract/progress run passed 22 tests with one disposable-SQL test
skipped because that invocation did not enable SQL; that SQL path passed in the prior 105-test run.
This prevents a failed recovery transaction or lost-response lookup from falsely acknowledging the
previous failed operation as a newly accepted send.

One bounded equivalent local run with 2,242 fabricated recipients (`python -B -m
tests.measure_campaign_acceptance`), external network forbidden:

| Stage | Released logic | Fixed logic |
|---|---:|---:|
| Review / verification / persisted snapshot | 274.26 ms | 318.60 ms |
| Durable acceptance | 37.24 ms | 28.48 ms |
| Worker claim and preparation | 65.51 ms, rejected | 839.34 ms, 2,242 jobs published |
| Provider submission | none | 23 fake batches, 2,242 fake acceptances in 5,271.65 ms |
| Progress read | 4.61 ms | 7.99 ms |

This demonstrates the repaired failure boundary, not faster live provider throughput. The
fixed direct-dispatch measurement ends at SENDING with all fake receipts accepted; final worker
completion is covered separately. Actual live review, queue wait, provider and UI timings after
release remain unverified. Main worker maintenance and its 30-second cycle can still add delivery
latency; preparation polling is isolated, delivery ownership has not been redesigned.

Topology validation, git diff --check and Studio Verify passed (syntax, Studio tests, secret scan).
Git fetch confirmed origin/main d8e498513131ac97d3368e6884ca7b1eddc9a0dd. All existing changed
CRM runtime modules match latest released source before this task's patch; no integration conflict
was found. Task base remains the Studio-approved 6e2805d058713cc64cfa70e7a85ee23ea66db7e1.

## Release and rollback, pending explicit approval

1. Preserve this task worktree and original occupied EMAIL/category work. With approval, commit
   only the listed campaign files/tests/migration/documentation. Integrate onto the current main
   revision without reverting mailbox or unrelated released changes; recheck exact candidate and CI.
2. Apply only the reviewed recovery migration through the normal migration workflow. It is
   backward compatible; old web code cannot invoke the new explicit recovery flow.
3. Release the actual CRM worker first, then canonical primary web service, at the tested revision:
   sports-cave-seo-worker srv-d9ujm9navr4c73amurgg and sports-cave-os srv-d8kl4on7f7vs73dvavv0.
   Do not deploy webhooks, SEO cron or create/replace services; no Blueprint sync or env changes.
4. Verify exact revisions and effective public sender/reply-to consistency. Recheck the live campaign
   still has zero recipient work. Re-review the original campaign and explicitly confirm recovery,
   dispatching at most its original 2,242 reviewed recipients who remain eligible. Do not duplicate it.
5. Observe the same operation through preparation, unique recipient jobs, Resend acceptances,
   webhook delivery and main-page final status. Never interpret SMTP/provider acceptance as delivery.
   Preserve uncertain outcomes for reconciliation; never clear queues or blindly resend.

Verified rollback anchors at preparation time:
- web: 6661eb6bf3ea8bfe6762273245f57124e952e38f, dep-dbfu801srm7s73buiqm0;
- worker: 05a0b87d205a668ebe2508303ae797a9b804e639, dep-dbft45tg1s2s73es954g.

Rollback only affected services to those immutable revisions after checking current deployment
state. Keep the backward-compatible migration and all immutable snapshots/receipts/history.
Do not reset campaign/preparation statuses or delete jobs. Old worker preparation may reject
new contract snapshots safely; already published frozen dispatch remains compatible. If release
or recovery fails, hold further recovery and inspect existing operations, not a duplicate send.

The owner subsequently explicitly approved this prepared release and original campaign recovery/send.
The following evidence records that authorised execution; the preparation section above is historical.

## Approved live release and original campaign recovery

27 October 2026, Australia/Sydney (AEDT, UTC+11). Source revision
191b118594808fcf6453e7a3d0d84116f41d3f2b is on GitHub main. It contains only the 20 campaign
implementation/test/documentation files above relative to released main; prior mailbox and other
released work was merged intact. The occupied EMAIL category worktree was not changed.
The integrated revision passed 123 focused tests in 22.322 seconds and Studio Verify.
No main-branch campaign CI workflow exists; the repository's only Actions workflow targets a
separate image-prompt feature branch. Local checks were run on the exact source revision.

The reviewed recovery migration was applied through Supabase apply_migration and the installed
function guard was read back. No production environment variables or service topology changed.
Both approved existing services were deployed deliberately; skip-render commit markers avoided
unrelated automatic service deployments:

- CRM worker: dep-dbfv5459fdbs73c9br50, live 11:39:54 AEDT, instance g6mgn.
- Primary web: dep-dbfv5q1srm7s73c1bqkg, live 11:43:03 AEDT, instance vf4cl.
- Read-only worker runtime verification confirmed source revision, sender
  Sports Cave <hello@sportscaveshop.com>, reply-to hello@sportscaveshop.com, and matching production
  settings for the original review. No credentials were printed or copied.
- Public /_stcore/health returned HTTP 200 / ok (317 ms from Windows).

The new main-page Re-review & resume action was used once, followed by one Send confirmation.
Snapshot 3c9ac86c-6ac3-4784-a062-b294b7908718 retained the exact original content (ignoring counts),
and its recipient list was verified as a subset of the original reviewed list. Draft version remains 19.
The fresh audience had 2,302 members, 2,242 eligible before recovery intersection, and 60 exclusions;
intersection retained 2,241 eligible original recipients and excluded one additional outside-original
identity. No recipients were added. No duplicate campaign was created.

Recovery operation: 345b8cef-7df3-4594-b13e-34c516bf81b0.
Campaign send ID: 0817eed1-4a18-5038-9d29-7db1f72ab304.
Exactly one recovery acceptance and one preparation attempt were recorded.
The prior failed operation/snapshot remain in history. Refresh during sending retained the same
operation, and the main page advanced through Verifying and Sending without another submission.

Actual live timing evidence (AEDT):

| Event | Time / duration |
|---|---|
| Re-review click invoked | 11:43:42.392 |
| Review job began | 11:43:50.524 |
| Authoritative audience work | 35.796 s, 151 Shopify GraphQL requests, 3 database queries, 0 provider requests |
| Review job complete | 11:44:36.951; 46.428 s total |
| Send click invoked | 11:45:05.580 |
| Disabled control and Submitting observed | by 11:45:06.016 (tool-observed upper bound 436 ms) |
| Acceptance transaction timestamp | 11:45:06.791656; 1.212 s after click invocation, not an exact commit-latency measurement |
| Worker claim timestamp | 11:45:11.582868 |
| Publication / all recipient jobs timestamp | 11:45:49.093929; 42.302 s after acceptance transaction timestamp |
| First provider-submission boundary | 11:46:35.356194; 88.565 s after acceptance timestamp |
| First delivered event | 11:46:39.307 |
| Last acceptance receipt | 11:53:41.926301; 8 min 35.135 s after acceptance timestamp |
| Worker marked SENT | 11:57:02.483239; 3 min 20.557 s after last acceptance receipt |

All 2,241 recipient rows are ACCEPTED with 2,241 distinct provider IDs and zero duplicate recipient
groups. All 23 batch manifests are ACCEPTED, attempt_count=1. No pending, failed, blocked or uncertain
submissions remain. Provider logs show HTTP 200 batch responses and no individual-email submission
calls. No blind retries or manual queue/status resets were used.

Direct read-only Resend GET /emails/01a17ad2-ca85-7be8-8100-416ebc8dfd7f confirmed last_event=delivered
for an actual broadcast message, created at 11:46:37.482 AEDT. At approximately 11:55 AEDT, the
signed callback ledger matched by stored provider ID contained delivery evidence for 411 recipients,
five bounces and two delayed-delivery events. These are observed partial callback counts, not a claim
that every accepted message was delivered. Recipient addresses and email bodies were not exported.

Remaining measured limitations: the required fresh audience review still takes about 46 seconds.
The shared worker paused between its bounded dispatch passes for maintenance; the two passes took
128.554 s (1,200 recipients) and 123.981 s (1,041 recipients), with a multi-minute gap between them.
Per-batch database/claim writes took roughly 5–10 seconds, while typical provider requests took
0.75–0.9 seconds. Final campaign status is updated later in the worker cycle. Delivery/open/click
counters also lag verified callback arrival because the existing webhook reconciliation queue
processes events separately (627 campaign events were pending at 11:53:21 AEDT). These remaining
latencies were observed, not hidden by optimistic success labels, extra submissions or status resets.

The worker naturally marked the campaign SENT at 11:57:02.483239 AEDT; no manual status mutation
was used. The signed-in main Campaigns page automatically showed Sent and Active 0. The original
campaign was retained, with 2,241 unique accepted receipts and no duplicate jobs or second send.

### Tested local follow-up: immediate confirmed completion

Live evidence exposed a separate final-status delay: Engine.tick marked completed campaigns only
after unrelated source maintenance, 200.557 seconds after this campaign's last acceptance receipt.
The local crm_engine.py follow-up extracts the existing guarded completion statement into
complete_campaigns() and also invokes it immediately after the existing leased dispatch checkpoint.
It preserves the same terminal checks: PENDING, CLAIMED, SUBMITTING and UNCERTAIN prevent completion;
provider-ID-backed acceptances determine the final accepted count. Existing worker-cycle completion
still calls the same helper. No sending, eligibility, recipient selection or retry rules change.

45 focused checks passed in 10.305 seconds: tests.test_crm_campaign_completion,
tests.test_crm_batch_dispatch and tests.test_crm_send_progress, with disposable SQL enabled.
The new checks prove completion runs before returning to maintenance and that pending/uncertain
recipients remain active. The owner subsequently explicitly approved committing, pushing and
deploying this follow-up to sports-cave-seo-worker only. Rollback remains revision 191b118.
No migration or production configuration changes are required. The already completed original
campaign requires no resend or recovery; no new campaign is submitted for verification.

### Follow-up release verification

The owner's fresh worker-only approval was received and executed on 27 October 2026.
Source 356ae9c9e0e1765442318a52eb1a600433a6c28e was committed and pushed to GitHub main.
The exact committed source passed the same 45 checks in 9.625 seconds against a fresh disposable
SQL fixture, plus Studio Verify, secret checks, git diff --check and topology validation.
The source delta from the initial live release is only crm_engine.py; the other two changed files
are the completion regression tests and this evidence record.

Render worker deployment dep-dbg0de942hec73d70m80 is live at that exact revision, finished
13:05:57.376160 AEDT. Instance stx4v started sports_cave_worker.py at 13:05:59.800 and its CRM child
at 13:06:00.783. The bounded startup log check found no matching traceback or worker-cycle failure.
The canonical primary web service remains on the initial 191b118 deployment; it was not redeployed.
No other service, production configuration or migration was changed for this follow-up.

Post-deployment SQL reconfirmed the original campaign remains SENT with its unchanged
11:57:02.483239 AEDT timestamp, 2,241 recipient jobs, 2,241 distinct accepted provider IDs,
zero other recipient statuses, and exactly one recovery acceptance. The completed campaign was
not submitted or retried. At 13:04 AEDT the received callback ledger contained 958 delivered,
11 bounced, 16 delivery-delayed and one complained recipient; callback counts remain asynchronous
and event types are not mutually exclusive. No claim is made that every accepted message arrived.

Completion ordering and pending/uncertain guards were verified without delivery. No additional
live campaign was sent to benchmark the new completion latency. Fresh-audience verification,
shared-worker maintenance between dispatch passes, database connection overhead and callback
reconciliation throughput remain the measured performance limitations described above.
Rollback for this worker-only release is 191b118594808fcf6453e7a3d0d84116f41d3f2b; retain all
receipts and immutable campaign history if rollback is needed. No rollback was necessary.
