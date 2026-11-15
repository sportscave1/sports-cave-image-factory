# Email automation and campaign reliability repair — 9 October 2026

Local changes only. No emails, live subscription changes, flow publication, activation, consent changes, historical enrollment, commits, pushes or deployments were performed. Production access was read-only. Earlier uncommitted Post Ad work is preserved separately.

## Production evidence and root causes

Inspection used Nathan's Render workspace and the existing CRM Supabase project `ceyzbfpuwuuxaiqwiltz`. All three inspected Render services were running commit `675342a8ce33c8fc932a6458c4bdac8130cc6c6f`, also the local pre-repair HEAD. Evidence timestamps below are UTC on 8 October 2026 (9 October in Sydney).

| Finding | Evidence and conclusion |
| --- | --- |
| Checkout webhooks are working now | The canonical app's saved diagnostic at 21:51:12 verified checkout-create, checkout-update, order-create and paid-order subscriptions, app identity, HMAC configuration and callbacks. Signed checkout and paid-order records continued arriving around 21:32. The October 5 missing-checkout diagnosis is obsolete. |
| Published timing differs from the draft | The one active native abandoned-checkout flow, “Abandoned Checkout — Wall Preview 1”, is published v2 with only Email 2 enabled and a **1,860-second / 31-minute** delay. Its draft has Email 1 disabled at 600 seconds and Email 2 at 43,200 seconds. A draft 10-minute value cannot control the published sequence. No business settings were changed. |
| Maintenance delays delivery | Worker cycles in the sampled 20:00–21:52 logs ran about 62–283 seconds, before the existing 30-second idle wait and other worker tasks. One checkout-cache page processed 72 unchanged rows between 21:53:06 and 21:55:12. The original loop dispatched frozen campaigns after cache refresh and source reconciliation. |
| Healthy long cycles could look like outages | The five-minute schedule guard originally checkpointed only once near the start of a cycle. A 283-second cycle plus a 30-second wait exceeds that threshold. The defect was reproduced locally; **no currently missed scheduled campaign was found in the production snapshot**, so it is not proof of a particular historical missed send. |
| Optional pixel failures add unnecessary work | Logs repeatedly showed `automation app pixel` / `ShopifyAPIError`. This check does not gate server-side checkout triggers. Its exact Shopify error cause was not exposed in the sanitized logs. It remains available in explicit diagnostics. |
| Transient database failures affect manual polling | Logs included `ConnectionTimeout` immediately before `checkout_enrollment_poll_failed StoreUnavailable`, plus several `OperationalError` entries. These establish a connection/operation problem, not missing-table evidence. No queued/checking manual requests were stuck in the observed snapshot. The deeper infrastructure cause remains unverified. |
| Terminal campaign naming could mislead | One older campaign was stored as `SENT` with zero accepted recipients and four `revalidation_unavailable` failures. Completion labels now flag zero acceptance rather than claiming a successful send. Historical status and receipt records are retained. |
| A legacy source failure could stop a cycle | Unlike native flows, a legacy automation source exception could escape reconciliation and prevent later campaign completion/maintenance. Source errors are now isolated for both kinds of flow. |

At the snapshot there were 38 completed checkout journeys, no active journeys, 3,162 non-test accepted sends and four failed sends. Nine manual requests were completed (two with eligibility blocks) and one had expired. These are point-in-time aggregate observations, not proof that every eligible checkout was enrolled. Resend delivery events were present, but acceptance totals must not be equated with delivery totals.

## Shopify subscriptions and exact remaining changes

All verified subscriptions below use delivery API version **2026-04**, without detected duplicates.

| Topic | Observed state | Callback |
| --- | --- | --- |
| `CHECKOUTS_CREATE` | Verified | `https://sports-cave-os-webhooks.onrender.com/webhooks/shopify/crm` |
| `CHECKOUTS_UPDATE` | Verified | Same CRM receiver |
| `ORDERS_CREATE` | Verified | Same CRM receiver |
| `ORDERS_PAID` | Verified | `https://sports-cave-os-webhooks.onrender.com/webhooks/shopify/orders-paid` |
| `ORDERS_FULFILLED` | **Missing** | Create at the existing CRM receiver after separate approval |
| `CUSTOMERS_EMAIL_MARKETING_CONSENT_UPDATE` | **Missing** | Create at the existing CRM receiver after separate approval |

The missing topics prevent the fulfilled and welcome triggers from passing their existing capability gates. They do not explain the active abandoned-checkout flow's published timing. `read_orders` and `read_customers` were already verified; **no additional permissions are evidenced as necessary** for these six server triggers.

The exact proposed Shopify change is to add only the two missing topics, using the canonical app and JSON delivery to the existing CRM callback at 2026-04. First re-inspect with `python scripts/register_crm_webhooks.py --automation-only`. After a separately approved change window, that existing script's `--apply` option creates missing topics only and re-verifies callback/version. Re-check the dry-run output immediately before applying; do not recreate the four working subscriptions.

No mandatory app code/theme/extension deployment is identified for these server triggers. The optional pixel remains unverified; its repeated API error does not establish that an extension update is required. Investigate that separately before proposing any pixel activation or app update.

The existing registration mutation was schema-validated against 2026-04, without execution. Shopify reports `endpoint` deprecated in favor of `uri`; the existing supported query was retained to avoid an unrelated API rewrite. Topic/scopes reference: [Shopify 2026-04 webhook topics](https://shopify.dev/docs/api/admin-graphql/2026-04/enums/WebhookSubscriptionTopic).

## Local implementation and safety

- The existing `crm_worker.py` / `sports_cave_worker.py` deployment remains the only delivery infrastructure. No new worker, background sender or Render service was added.
- Due automation and campaign work is checked before checkout maintenance, at cooperative boundaries during cache processing and abandoned-checkout evaluation, and after reconciliation. Checkpoints use the same engine and durable claims; they run outside checkout database transactions.
- The existing worker lease is renewed and the schedule guard checked at real work boundaries, at most once per minute. Delivery checks during maintenance are bounded to a 30-second cadence. These are opportunities to dispatch, **not a guaranteed 30-second SLA**: an individual blocking API/DB operation can still delay progress.
- A genuine gap over five minutes, disabled marketing, lost lease or failed verification still fails closed. No code resets missed/blocked campaigns to pending. There is no independent heartbeat that can conceal a stuck worker.
- Existing timeout, consent, suppression, purchase/recovery revalidation, snapshot, claim, idempotency and retry behavior is retained. Individual ambiguous submissions stay uncertain. Frozen campaign batches retain their bounded same-payload/same-idempotency-key retry contract; a new send identity is not created to retry an uncertain result.
- The redundant insert for an already-locked existing checkout is skipped. Identity, redaction, signed completion, order evidence and accepted-send checks still run. Cache timestamps now distinguish page start from successful completion. The original scan cadence is preserved so this reporting change cannot delay discovery.
- The automatic future-only cutoff (`checkout-auto-start-v2`, observed 2026-10-05 22:59:03 UTC), activation boundaries, existing recovery policy, disabled steps, paused flows and unpublished edits remain unchanged. Original published timing and every enrollment's immutable sequence remain authoritative. A 10-minute v2 published delay remains exactly ten minutes, without an added legacy hour.
- The worker refreshes required Shopify capabilities as before, but the optional pixel query runs through explicit diagnostics instead of every five-minute worker refresh. Last pixel status and its own timestamp are retained rather than falsely refreshed.
- Read-only diagnostics expose effective published and draft steps, relevant webhook time, cache completion, worker/checkpoint freshness, persisted due/retry times, enrollment evaluation reasons and accepted/failed/blocked/uncertain counts. Campaign history adds frozen local/UTC scheduling, worker status, accepted receipts, delivery events and missed/blocked reasons. Opening diagnostics cannot publish, enroll or send.
- Zero-acceptance terminal campaigns show “Needs attention” in the home table and completion view. Stored historical terminal statuses are preserved. Provider acceptance and delivery receipts are displayed separately, with duplicate delivery events counted once per recipient.

## Performance evidence

`scripts/benchmark_email_maintenance.py` runs both the committed baseline and modified checkout mirror against fabricated rows in loopback PGlite. Twelve unchanged checkouts, three runs per implementation, with a controlled 20 ms cost per SQL statement including transaction boundaries:

| | Before | After |
| --- | ---: | ---: |
| SQL statements/page | 72 | 60 |
| Median page time | 1,762.06 ms | 1,313.77 ms |
| Samples | 1,603.81 / 1,766.31 / 1,762.06 ms | 1,414.15 / 1,313.15 / 1,313.77 ms |

This is 16.7% fewer statements and about 25.4% lower median time in this controlled fixture. It is not a production benchmark or a promised end-to-end speedup. No production-after timing exists because nothing was deployed. The SQL delivery test independently verifies that a campaign is accepted before entering checkout maintenance and is not submitted again on the next cycle.

## Verification

Every test uses fabricated local data and mocked Shopify/Resend. A fresh-fixture runner is included because reusing a database across broad suites can retain suppressions, audience history and queued work and contaminate later tests.

| Final verification | Result |
| --- | --- |
| Delivery-focused suites, fresh database | **376 passed**, 76.815 seconds |
| Final ten-minute timing / checkpoint / receipt checks | **18 passed**, 2.939 seconds (overlaps focused coverage) |
| Full CRM discovery, fresh database and frozen source files | **1,071 run: 1,049 passed, 11 failures, 10 errors, 1 skipped**, 123.857 seconds |
| Original committed-code comparison | All **21 remaining failed test names** reproduced there; no newly failing names in the final run |
| Browser checks | Existing toolbar and new diagnostics both passed |
| Static checks | Python compilation and `git diff --check` passed |

**The broad CRM suite is not green.** Remaining failures concern outdated in-memory webhook mocks (five), global email defaults/sections (four), retired workspace UI selectors/expectations (three), storage manifest/UI expectations (three), built-in template expectations (two), and one each for preview source text, the old automation configuration panel, footer unsubscribe markup and preflight asset attribution. These were retained, not removed or hidden. They need separate triage; no unrelated email content or authoring behavior was changed to make them pass. The skipped test requires named-fragment support unavailable in the installed Streamlit and identifies its tested native fallback.

Exact failing tests, baseline comparison and run counts: [test-results.json](email-reliability-evidence/test-results.json). Local measurement samples: [maintenance-benchmark.json](email-reliability-evidence/maintenance-benchmark.json). Fabricated UI capture: [diagnostics-desktop.png](email-reliability-evidence/diagnostics-desktop.png).

Reproduce the focused run with `.venv/Scripts/python.exe scripts/run_email_reliability.py`; add `--all-crm` for broad discovery. The runner starts and stops a fresh in-memory SQL fixture automatically. The baseline comparison loads committed code in memory without reverting working files; its one source-inspection artifact is noted in the evidence and is not among the final 21 failures.

The initial 300-test focused baseline had 297 passes, two failures and one error: an obsolete 20-table assertion (24 tables now), a removed UI entry point, and a timing test that moved the persisted deadline twice. These tests were corrected without removing coverage or weakening delivery validation. A scheduled worker fixture also now calls the actual production claim predicate rather than a simplified SQL claim that accidentally bypassed the frozen-batch exclusion.

The existing automation toolbar browser suite passed, including publication/pause/resume **in the disposable fixture only**, desktop alignment and widths down to 320 px. The new diagnostics browser test passed with external network blocked, confirming published/draft separation, zero acceptance, unchanged lifecycle controls and 1440/1024/750/390 px layouts. `git diff --check` passed.

## Files changed for this task

Application: `crm_engine.py`, `crm_checkout_analytics.py`, `crm_automation_runtime.py`, `crm_automation_capabilities.py`, `crm_email_diagnostics.py` (new), `crm_automation_diagnostic_ui.py`, `crm_automation_toolbar.py`, `crm_campaign_progress.py`, `crm_campaign_progress_ui.py`, `crm_campaign_home.py`.

Tests: `tests/test_crm_email_reliability.py` (new), `tests/test_crm_email_diagnostics_ui.cjs` (new), `tests/test_crm_automation_diagnostics.py`, `tests/test_crm_automation_timing.py`, `tests/test_crm_checkout_reliability.py`, `tests/test_crm_postgres.py`, `tests/test_crm_production_v2.py`.

Tools and documentation: `scripts/run_email_reliability.py` (new), `scripts/benchmark_email_maintenance.py` (new), this report and its evidence files. Earlier Post Ad modifications are not part of this email repair.

## Deployment order and remaining limitations

1. Review the local diff, focused results and remaining broad-suite failures. There is **no new schema migration**. Verify the existing CRM migrations against the canonical database in read-only mode; do not re-run historical data updates casually. The current primary Render pre-deploy command targets an unrelated single migration, so it must not be assumed to verify the CRM migration chain.
2. After separate deployment approval, deploy the reviewed code to the existing `sports-cave-seo-worker` and `sports-cave-os`. Worker first gives the new checkpoint/completion observations; the UI is backward-compatible with older state. There is no receiver change requiring a `sports-cave-os-webhooks` redeploy and no Render Blueprint/topology change.
3. Observe normal new activity and aggregate timestamps/read-only logs. Check schedule checkpoint spacing, completion latency, fresh capabilities, expected published delays and acceptance/delivery evidence. Do not run a historical batch, auto-release missed campaigns, change marketing flags or send an unsolicited customer test.
4. In a separately approved Shopify change window, add only the two missing webhook subscriptions after a fresh inspection. Then verify new signed events. Publishing timing changes or enabling the disabled first email is a separate business decision and is not part of deployment.

Still unverified: production performance after deployment; the infrastructure cause of intermittent connection failures; optional pixel readiness; live delivery for the two missing triggers. PGlite exercises real PostgreSQL SQL, but its serialized test adapter is not a substitute for a multi-process production load test. Existing durable database claims and provider idempotency remain essential. A stale worker or uncertain provider outcome must be investigated, not bypassed with another send.

**Single safest next action:** review this local repair and its regression evidence before authorizing deployment to the existing services. Leave Shopify changes and flow publication for separate approval.
