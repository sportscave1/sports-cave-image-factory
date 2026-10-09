# Meta Posting regression investigation and local repair — 9 October 2026

## Outcome and limits

Implemented locally; not committed, pushed or deployed. No live Meta campaigns, ad sets, ads, assets or database records were created or changed. Production investigation used read-only Render history/logs and Supabase SQL/log queries. Posting tests used mocks and disposable local PostgreSQL. This repair does not redesign the Posting page or alter advertising payloads, content, targeting, budgets, templates, Carousel structure or activation behavior.

**Proven database condition:** concurrent executions of the Ads migration batch deadlocked in production, including during the Captains posting window. Normal posting and status reads unnecessarily executed migration DDL. The DDL defect already existed in the working version; commit `01bc5268b8e05d28947a17b5a9973827922be9a0` added background posting with frequent status polling, increasing concurrent exposure to that defect. This is a supported regression mechanism, not proof that this commit alone caused every reported timeout.

**Captains Ad 1 cause remains unproven:** the previous generic exception handler destroyed the diagnostic evidence. The persisted image hash narrows the failure to the image checkpoint/Page-photo portion of the first-ad flow. Production deadlocks overlap this interval, but there is no submission-correlated traceback proving which exception stopped that run. There is no evidence establishing a Meta API rejection.

**The original Captains run is not yet cleared for retry.** Its missing Page-photo ID does not prove that no Page photo was created. Live Meta ownership, configuration and PAUSED status could not be verified from this environment: no local Meta credentials or authenticated browser were available, and existing Render SSH authentication returned `Permission denied (publickey)`. The repair blocks blind retry of legacy generic failures. It does not replace the saved campaign or ad set.

## Deployment and source comparison

Times below are UTC; Sydney is UTC+11 on these dates. Source: Render deployment history for canonical service `sports-cave-os` (`srv-d8kl4on7f7vs73dvavv0`), Git history, and persisted submission timestamps.

| Version | Production evidence | Interpretation |
|---|---|---|
| `243263647e1479c4196ce28eadd54212809e3c19` | Live 7 Oct 02:24:27–05:27:22; deployment `dep-db2qpfbl550s73c52q9g`. Submission `721597b9-6ef7-4cd3-94a1-6c236b5d1919` completed three IE ads at 02:47:15. | Last confirmed working deployment on 7 October. |
| `2f6adbdd9d63fed0b0627083a4a8de1971379c8a` | Live 8 Oct 01:36:23–02:54:03. Submission `32f77679-3a1f-4ad0-b153-cb863b1bae75` completed three IE ads at 02:12:06. | Additional successful run before the background-job change. |
| `01bc5268b8e05d28947a17b5a9973827922be9a0` | Live 8 Oct 03:33:07; deployment `dep-db3gsgqjnfac738bdbcg`. | Introduced background jobs, reservation/hydration/status reads and two-second polling, all reaching the existing DDL path. |
| `72cabec21aca86beac17e0e6c762672542f30d51` | Live 8 Oct 22:52:03. | Compact Posting UI upgrade. |
| `736cd66e589771d5eb95f262b24d5c28e856c52f` | Live 8 Oct 23:03:14; deployment `dep-db420v0jo6nc73bmgaf0`. | Production version during the Captains failure on 9 October Sydney time. |
| `5da26f0e68dff56831a611c7d9d9b25d84c3049f` | Live 9 Oct 00:10:01; deployment `dep-db430ap42hec73c4enjg`. | Email changes committed/deployed by another actor during this investigation. No Meta file changes; after the reported failure. This repair was not deployed. |

The Oct 7 working version and incident version have no differences in `requirements.txt`, `requirements.lock`, `pyproject.toml`, `render.yaml`, `meta_ads_client.py` or `meta_collection_template_copy.py`. The main Meta creation loop and generic exception handler predate the regression; the relevant service additions were reservation, lookup and hydration. `ensure_ads_schema()` was identical in both versions and executed all ten Ads migration files on every call, after base schema initialization.

Current Render configuration inspected: Python service, `pip install` requirements build, `python sports_cave_server.py` start, pre-deploy command `python run_migrations.py --only 20260901_os_repair_requests.sql`, one Standard instance in Oregon. No topology change was made. Historical secret values/environment edits and installed package drift cannot be established from these interfaces; unchanged tracked requirements alone does not exclude runtime drift.

## Database evidence

Supabase PostgreSQL logs, 8 October UTC:

| Time | Evidence |
|---|---|
| 23:48:24.373 and 23:49:36.773 | `deadlock detected`, SQLSTATE `40P01`, `ALTER TABLE`; two sessions executing `20260626_ads_intelligence_v2_breakdowns.sql`, mutually blocked on `AccessExclusiveLock` for relation 52025. Catalog lookup identifies this as `meta_creative_tags`. |
| 23:44:25.364 and 23:46:03.395 | Additional deadlocks involving relation 50272 (`app_sync_state`). |
| 23:44:44.365 | Deadlock involving relation 50176 (`edition_products`). |
| 23:43:29.615 | SQLSTATE `57014`, statement timeout for `ALTER TABLE edition_products ADD COLUMN IF NOT EXISTS shopify_product_id TEXT`. |
| Incident window | Further timer/permission reads and sync-state writes timed out. Render recorded an orders count `QueryCanceled` at 23:44:11, duration 7,596 ms. |

This establishes database contention beyond Meta. `IF NOT EXISTS` does not make repeated DDL lock-free: ALTER TABLE commonly needs an AccessExclusive lock, which conflicts even with readers. See [PostgreSQL explicit locking documentation](https://www.postgresql.org/docs/current/explicit-locking.html).

The screenshot's start timeout cannot be matched uniquely to one SQL request because the old logs lack a submission correlation ID. It is therefore not claimed that one specific background operation or migration caused that individual timeout. A later activity snapshot showed no active lock waits; an idle transaction holding an advisory-lock query was observed, but is not evidence that it caused the earlier failures.

Migration history included CRM/email/wall-preview work and four Edition migrations applied 8 October at approximately 07:38:16 UTC: `20261008041452_edition_version_transitions.sql`, `20261008045733_edition_version_guard_hardening.sql`, `20261008065000_explicit_edition_cursor_override.sql`, `20261008090000_edition_admin_cursor_repair.sql`. No new Ads migration was introduced between the compared versions. Only the first three June Ads files were represented in the migration ledger; later Posting schema already exists physically through prior runtime initialization. No migrations or ledger modifications were applied during this investigation.

## Captains run and complete flow comparison

Submission: `3c72eb1a-e718-491d-b0fa-1e6bf8c8f917`.
Created 8 October 23:47:59.831253 UTC; last update 23:49:40.869451 UTC; ledger status FAILED.

| Resource | Persisted evidence |
|---|---|
| Campaign | `120250356896580554` |
| Ad set | `120250356897200554` |
| Ad 1 image hash | `fdbac44f77f0c72f26869b46d5c4d452` |
| Page photo, canvas elements, IE, creative, advertisement | No IDs persisted for Ad 1 |
| Other ads | Ads 2 and 3 pending |
| Actual configured status | Campaign/ad-set configured-status fields empty; ledger alone does not verify PAUSED |

The working and incident creation flows use the same advertising operations:

1. Validate input, destination and Meta configuration; reserve/claim submission.
2. Create or select the campaign, then create or select its ad set; preserve PAUSED creation.
3. For each of three IE routes: upload image, persist hash, upload Facebook Page photo, create photo/product/button/footer canvas elements, create IE, verify destination/provenance, copy the proven template ad, associate/verify the correct creative and canvas, verify PAUSED status, checkpoint results.
4. Verify final objects and save completion. Carousel retains its separate existing card/order workflow.

The incident version added asynchronous orchestration and polling around this flow, but did not change its Meta payloads. Before this repair, each checkpoint and status lookup could execute the migration batches again. Unexpected database/Python failures were flattened into “The Meta request failed.”

For Captains, the image upload returned a hash. The generic failure handler could persist that in-memory hash even if its preceding `IMAGE_UPLOADED` checkpoint failed. Thus the hash does **not** prove that checkpoint committed, nor does the absent photo ID prove the photo upload never happened. Canvas creation, template-copy and ad creation are later in the flow and are not evidenced by this ledger. Exact first-ad causation is irrecoverable from the retained generic message alone.

## Targeted repair

- `ensure_ads_schema()` now performs bounded, cached, read-only schema readiness checks, never base bootstrap or migration DDL. One positive check per database target per 60 seconds; a changed target, expired cache or prior failure revalidates. Missing required tables/Posting columns fail closed with an administrator-action message. No new migration is required for the recovery journal, which uses existing JSON storage.
- Each existing Meta write records a durable intent before the HTTP operation and records its returned ID/hash afterward. The journal stores operation identities and returned IDs, not uploaded bytes, request payloads or secrets. It is partitioned by original ad route, preserving three distinct IE resources. Generated start times and upload filenames cannot accidentally turn a retry into a new operation.
- Known completed operations reuse their recorded IDs. Explicit API rejections may be retried. Pending intents, lost write responses, successful responses missing IDs and legacy generic failures stop for reconciliation; they are never blindly replayed. The existing template-copy reconciliation remains available when it can verify a returned route copy.
- SQL updates enforce the worker's current, unexpired lease. A stale worker cannot overwrite another worker or a committed terminal result. A late coordinator error cannot replace COMPLETE with failure. Successful checkpoints remain authoritative even if their acknowledgment is lost.
- Resume uses the original submission ID and request fingerprint. After a process restart, the original upload buffers must be restored by the user; a changed request is rejected. Known campaign/ad-set ownership, configuration and run-owned PAUSED status are read back before further writes. Saved image, Page-photo, IE, creative and ad identities are checked where recorded. Existing destination/provenance checks remain in place.
- Unexpected failures log exception class, safe traceback locations, operation, submission ID, SQLSTATE and available Meta code/subcode/trace ID. Logs omit exception payloads, source lines, local variables, tokens and creative/customer content. UI distinguishes checkpoint/internal failures from genuine Meta API errors and avoids asserting PAUSED before verification.
- `scripts/audit_meta_posting_run.py` supplies GET/SELECT-only checks in an environment with existing secured credentials. It neither clears errors nor approves retries. For the Captains run, missing resources still require operator reconciliation; running this script alone cannot prove that an unrecorded upload never occurred.

There is deliberately no global promise of exactly-once remote creation: a remote POST and local database commit cannot be atomic. The safety rule is to stop when the outcome cannot be established. Tests verify that such uncertain jobs do not automatically create duplicates.

## Verification and performance evidence

| Check | Result |
|---|---|
| Final focused regression run | **293 passed**, 29.022 seconds. Posting, recovery, jobs, progress, handoff, Carousel, template copy, diagnostics, crop/footer/image workflow and product URL tests. |
| Disposable PostgreSQL recovery tests | **7 passed**, 3.681 seconds. Real reservation/claim/checkpoint SQL, stale leases, lost commit acknowledgment, terminal preservation, legacy error guard and read-only schema check. |
| Earlier expanded suite | **481 passed / 3 failed**, 484 total, 155.732 seconds. All three failures reproduced against unchanged baseline `5da26f0` (3 tests, 9.987 seconds). They are existing unrelated Ads-page layout expectations; not weakened or edited. |
| Browser test | Passed: progress appeared in **112 ms** in the local mocked fixture; refresh restored the run, partial Ad 2 rejection safely retried, completed result survived refresh, no mobile horizontal overflow. Desktop 1280 px and mobile 390 px checked. |
| Syntax and whitespace | Python compilation and `git diff --check` passed. |

Fault injection covers campaign/ad-set checkpoints, image and Page-photo upload, canvas elements and IE creation/verification, copied-ad creation, persistence failures, rate-limit-style rejection, lost responses, process restart and repeated retries. Mocked recoverable jobs finish with three separately confirmed PAUSED ads under their original campaign/ad set. Unknown write outcomes do not replay. Recovery asset verification tests reject missing/mismatched resources and non-PAUSED saved ads without issuing POSTs.

Existing unrelated failures: `test_initial_setup_is_compact_and_optional_sections_start_collapsed`, `test_submit_supported_result_renders_compact_sections_with_url_parameters`, `test_submit_valid_category_campaign_renders_category_specific_output` in `tests/test_ads_page.py` (additional existing expander and outdated URL/code-block expectations).

Measured work reduction: ten Ads DDL batches per readiness call before, zero after. Thirty concurrent readiness calls in the local test produce one catalog SELECT. The journal adds two lightweight checkpoints per tracked remote write (58 for the normal mocked 29-write three-IE flow); this is an explicit durability tradeoff. No real production posting or before/after production loading benchmark was run because deployment and live test writes were prohibited. The 112 ms browser result is fixture feedback latency, not a claimed production speedup.

## Changed files

Application: `ads_schema.py`, `supabase_backend.py`, `meta_posting_recovery.py`, `meta_posting_service.py`, `meta_ads_client.py`, `meta_posting_jobs.py`, `ads_posting_page.py`, `ads_posting_progress.py`.

Tools and tests: `scripts/audit_meta_posting_run.py`, `scripts/run_meta_posting_browser.py`, `tests/test_meta_posting_repair.py`, `tests/test_meta_posting_jobs_sql.py`, `tests/test_meta_posting.py`, `tests/meta_posting_postgres_server.mjs`, `tests/meta_posting_progress_browser.cjs`, and this report.

Existing backend diagnostics, posting history, submission IDs and campaign/ad-set records are retained. Background base-schema DDL in unrelated modules was observed but is outside this targeted repair; eliminating the Posting DDL path cannot guarantee that unrelated database contention will disappear. The original Captains run remains blocked pending read-only Meta reconciliation and restoration of its original inputs. No deployment or live completion is represented as performed.
