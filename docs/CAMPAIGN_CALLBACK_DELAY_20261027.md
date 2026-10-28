# Campaign callback processing and counter refresh

Task: 20261027-c6d937eb. Owner: codex-callback-delay-20261027-01a157b1.
Branch: codex/task/email-batch-callback-reconciliation-and-prompt-c-20261027-c6d937eb.
Local implementation only; no commit, push, deployment, configuration change,
production write, callback replay, customer message or campaign duplication.

## Evidence and cause

Read-only production diagnostics on 27 October 2026 found 4,007 processed Resend
callbacks in the preceding six hours, averaging 901 seconds between durable receipt
and processing. The queue had caught up at that inspection; this is historical
burst lag, not a claim that every current callback takes 15 minutes. A subsequent
read at approximately 16:00 AEDT found 4,028 DONE events, average 897 seconds,
newest receipt 04:59:39.068462 UTC and processing 04:59:39.701898 UTC. No PENDING
events were returned for that six-hour cohort. Webhook logs also showed individual
processing operations around 2,010 ms.

The consumer opened a new transaction/connection per event and repeated the same
provider's complete event reconciliation for each event. HTTP admission also
opened new connections. After campaign submission ended, Home polled/refreshed
on its normal 20-second cache cycle; confirmed callback changes did not invalidate
the relevant cached projections. Neither issue changes SMTP/provider acceptance.

## Repair

- `crm_callback_store.py`: dedicated bounded callback pool, maximum four
  connections/four waiters, two-second checkout deadline, explicit transactions
  on autocommit connections. Reuses the existing psycopg_pool dependency. No
  automatic write retry after an unknown commit.
- `crm_http.py`: signed Resend receipt uses that transport. Raw-body signature,
  timestamp, admission limit, durable fact + queue commit before HTTP 200, and
  failure/backpressure responses remain intact. Shopify routes are unchanged.
- `crm_resend_event_worker.py`: claim at most 100 events using existing durable
  PENDING state and FOR UPDATE SKIP LOCKED; reconcile distinct provider IDs once
  per batch. Facts, suppression and DONE commit together. Savepoints and bounded
  splitting isolate poison events; failed events retain a delayed retry. At most
  24 reconciliation attempts per claim. Active draining pauses 50 ms; idle waits
  one second. Shutdown/crash retains uncommitted work. No email transport.
- `crm_workspace_store.py`: deterministic ordered per-provider advisory locks,
  avoid unchanged association rewrites, retain idempotent receipt joins and
  suppression rules. Persist a revision in existing crm_runtime_state in the same
  reconciliation transaction. Receipt publication after an early callback also
  advances this revision. No schema migration.
- `crm_campaign_callback_refresh.py` and `crm_campaign_home.py`: one pooled
  lightweight revision probe on the existing Home controller, every three seconds
  when visible rows have delivery state. Refresh only affected table/delivery
  projections, preserve last-good values and in-flight reads, avoid starving slow
  queries during continuous callbacks. First-probe and missing-revision races are
  covered. Existing hidden-page/dialog pauses, layout, authoring and send status
  remain intact. Counts reflect committed ledger facts.

## Focused verification

Disposable localhost SQL fixture with fabricated recipients and mocked delivery
transport only; no production credentials or provider calls in development.

1. `CRM_TEST_POSTGRES=1 python -m unittest tests.test_crm_callback_batch
   tests.test_resend_webhook_reliability tests.test_crm_workspace
   tests.test_crm_campaign_home`: 67 tests passed in 9.239 seconds.
2. After first-probe hardening, `python -m unittest
   tests.test_crm_callback_batch.CallbackRefreshTests
   tests.test_crm_callback_batch.CallbackPoolTests`: six tests passed, including
   two additional first-probe/failure regressions. No unnecessary repeat of the
   unchanged SQL suite.
3. Coverage includes 150-event bounded draining, per-provider deduplication,
   unchanged Sent campaign/accepted receipts, duplicate receipt, early callback
   association, partial poison failure, transaction rollback, lost commit
   acknowledgement, stop/restart retry, bounded failure splitting, complaint/hard
   bounce suppression versus transient bounce, pool commit/rollback/return,
   selective cache invalidation and retention after failed/slow reads.
4. Existing signed HTTP tests cover prompt durable acknowledgement, invalid
   signature, four concurrent admissions/backpressure, healthy health endpoint
   under load and retry after persistence failure.
5. `tests/measure_crm_callback_batch.py`: one bounded original/current comparison,
   each 100 events across 20 fabricated providers, same local database adapter.

   | Processing | Elapsed | Transactions | SQL statements | Delivered recipients |
   | --- | ---: | ---: | ---: | ---: |
   | Original | 1,315.06 ms | 100 | 600 | 20 |
   | Current | 32.42 ms | 1 | 10 | 20 |

   Statement totals concern the measured consumer only. Original worker AND
   original reconciliation SQL are loaded from the base Git revision; relevant
   callback code is identical in current released code. This fixture has no
   production network latency. Pool handshake savings are not measured here.
6. Actual headless Edge + Streamlit Home, `tests/fixtures/crm_callback_preview.py`
   and `node tests/measure_crm_callback_ui.cjs`: one before/after run, fabricated
   SQL campaign, external browser HTTP denied, fake dispatch only. Callback
   arrives on a background timer three seconds after the interaction's render;
   then the page updates automatically without a second click/manual refresh.
   Original scheduled-callback-to-counter: 20,484 ms. Current: 4,340 ms.
   Both timings INCLUDE the same 3,000 ms controlled arrival delay and local SQL
   processing. Reload retains count 1, same campaign ID, status Sent, one row.
7. Studio Verify passed syntax, Studio tests, changed-file secret heuristics and
   diff checks. `python scripts/validate_render_topology.py` passed. No Blueprint
   sync or infrastructure changes are part of this task.
8. Latest fetched origin/main: 2cffee6654b0c177592219a0c24736318bd01f9f.
   A temporary Git index containing that revision passes `git apply --cached
   --check` for the task patch, without changing the real index or checkout.
   Changed callback backend files also match the webhook service's currently
   released 05a0b87d205a668ebe2508303ae797a9b804e639 baseline. Released Home has
   additional nonconflicting recovery/status hunks: retain them during integration.

Limitations: PGlite executes real SQL but the test adapter serializes transactions;
it does not prove competing native PostgreSQL worker claims. Local Docker daemon
is unavailable and no native local PostgreSQL is installed. The connection pool
lifecycle has focused adapter tests, not a real remote pool saturation test.
Production post-release latency remains unverified. The unrelated existing
Shopify incomplete-order HMAC test returns 400 on both untouched baseline and
current code; it is outside this focused cohort and was not changed to hide it.

## Campaign preservation

Read-only recheck of campaign 3f61e092-26ec-57dd-9327-117bdd2ceb77:
SENT; sent_at 2026-10-27 00:57:02.483239 UTC; 2,241 recipient jobs;
all 2,241 ACCEPTED; 2,241 unique provider IDs. Identical to prior release evidence.
No resend, duplicate, reset, queue clearing, manual production reconciliation or
status update performed. October 7 unknown mailbox operation is untouched.
The existing dirty EMAIL category worktree is preserved separately.

## Prepared release and rollback (approval required)

No release has been executed. Fresh owner approval is required by AGENTS.md.

1. Review and commit only this task's listed source/tests/evidence; use the normal
   `[skip render]` release convention to prevent unrelated automatic service
   deploys. Integrate current main preserving previous mailbox/campaign releases,
   then run necessary checks on the exact release revision and verify clean state.
   Push only after explicit approval.
2. Deliberately deploy existing `sports-cave-os-webhooks`
   (srv-d9146onlk1mc739nrm7g) for callback HTTP/consumer code and existing primary
   `sports-cave-os` (srv-d8kl4on7f7vs73dvavv0) for Campaigns UI. No worker release
   is required: webhook_server.py starts this callback consumer. Do not deploy
   sports-cave-seo-worker or create/replace/rename any service.
3. No migration, environment, subscription, campaign or recipient changes. Deploy
   webhooks first; verify exact revision and health, batching logs, durable lag,
   retry/backpressure, then primary and confirmed counter refresh. Observe natural
   incoming callbacks; do not generate a customer/test campaign or resend Black
   Friday. Retain 2,241 unique accepted receipts and original sent timestamp.
4. Current rollback targets: webhooks deploy dep-dbft45tg1s2s73es94rg,
   commit 05a0b87d205a668ebe2508303ae797a9b804e639; primary deploy
   dep-dbfv5q1srm7s73c1bqkg, commit191b118594808fcf6453e7a3d0d84116f41d3f2b.
   Reverify these are still the previous live versions at release time. Roll back
   only affected services if new errors/health regression appear. Never revert
   accepted campaign work or remove callback rows. The revision key is harmless
   to old code and needs no rollback migration. Old consumer can drain all retained
   PENDING events; DONE and committed facts remain idempotent. No queue reset.
