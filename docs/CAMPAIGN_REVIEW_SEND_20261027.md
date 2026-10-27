# Campaign Review and Send repair — local release preparation

Task: 20261026-2398b49c. Owner: codex-campaign-send-20261027-01a157b1.
Branch: codex/task/email-campaign-review-and-send-verification-mism-20261026-2398b49c.
Status: implemented and tested locally; not committed, pushed, migrated or deployed.

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

Remaining gates: fresh project release approval for commit/push/migration/deployment and explicit
approval to recover/send this original broadcast. No claim of deployed repair or live campaign
completion is made before those actions and provider evidence.
