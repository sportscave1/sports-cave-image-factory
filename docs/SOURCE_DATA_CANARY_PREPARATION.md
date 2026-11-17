# Source repair release and financial canary preparation

Updated 6 November 2026. Local task `20261101-d2835a7c`, owner `codex-ai-20261102-01a19909`.
**Local implementation and read-only checks only. No commit, push, deployment, production DDL/write, backfill, resync, permission expansion or AI activation.**

## Completed / pending / blocked

- [x] Actual OS Shopify historical-order scopes and Meta account/Insights access checked in the existing trusted Render Web Shell; [exact repeat commands and separate results](RENDER_READ_ONLY_PREFLIGHT.md). This resolves the earlier unavailable-remote-execution blocker without exporting credentials.
- [x] New self-contained, sanitising preflight: `scripts/render_source_preflight.py`; six focused credential-free tests pass.
- [x] Financial-only apply/audit/rollback/reconciliation handler: `shopify_financial_canary.py`. Unwired: no connection creation, UI, scheduler, worker registration, provider calls, automatic retries, DDL or apply CLI.
- [x] Seventeen new native PostgreSQL synthetic tests pass. Actual transactions, audit persistence, two simultaneous connections, exact key-presence/null/zero restoration, protected related tables, guard-trigger rejection, stale/changed approvals/sources, partial apply/rollback recovery and lost commit acknowledgement are covered.
- [x] Six-order dry run refreshed using real **OS** Shopify credentials and a fresh explicit read-only ledger query; AUD **1,483.40** still proposed. Exact manifest and supporting evidence remain outside the preview.
- [x] Existing production table/trigger contract inspected read-only: existing `audit_logs` supports the journal. No new migration or hosting resource.
- [ ] Current-production-base integration and Python 3.12 exact-candidate acceptance. The current task has older-base and unrelated AI changes; it must not be released wholesale.
- [ ] A reviewed candidate commit/SHA. **None exists yet**; commit and push are unauthorised.
- [ ] Authorised deployment to the existing services and real database-role/backup acceptance.
- [ ] Fresh bounded six-order approval and production apply. Current review captures are older than five minutes and deliberately fail the execution freshness gate.
- [ ] Separate complete Meta day capture, attribution/Ads Manager comparison, then separately approved persistence. Successful access is not full reporting reconciliation.
- [ ] Full-day Shopify/refund coverage and regenerated numerical Daily Brief acceptance after approved source repair. Synthetic tests do not establish real business completeness.

No externally missing Shopify/Meta access permission remains for the tested scope. Actual update/insert privilege of the deployed database role and the full business-data reconciliation remain unverified. No permissions were expanded.

## Exact existing services

Read-only Render inventory and latest deploys were checked this follow-up. All three live revisions are `64ed998a7e5f26fefd2d559fc2d7bb1873e24832`; this is the **current production revision**, not a new candidate.

| Existing service | ID | Start command / plan | Why included | Current artifact |
|---|---|---|---|---|
| sports-cave-os | srv-d8kl4on7f7vs73dvavv0 | `python sports_cave_server.py` / standard | Manual order/Ads UI, shared backend, reporting refresh | dep-dbmegs95efls73e3trrg |
| sports-cave-os-webhooks | srv-d9146onlk1mc739nrm7g | `python webhook_server.py` / free | **Active periodic Shopify order writer** and webhook paths; must receive financial query/preservation repairs | dep-dblcdgm7bikc73ah4l1g |
| sports-cave-seo-worker | srv-d9ujm9navr4c73amurgg | `python sports_cave_worker.py` / starter | Shared `supabase_backend`/`shopify_sync` consumers in product onboarding and CRM; coordinated compatibility release | dep-dblcdgm7bikc73ah4kjg |

Ownership evidence: `webhook_server.py` starts `shopify_order_reconciliation_worker`; its bounded loop calls `sync_latest_paid_orders_to_supabase`. The named SEO worker supervises CRM and product onboarding; it is **not** the owner of that periodic order reconciliation loop. Deploying only the primary cannot repair the webhook writer.

Keep `sports-cave-seo-daily-sync` (`crn-d9ujqvvqj5pc73fpe0ag`) suspended; it is the existing Google SEO cron and is outside this release. Do not use older duplicate/studio services. Exactly one canonical primary remains. No service, plan, identity or Blueprint change is proposed; no new hosting cost. Existing compute, database and provider rate limits still apply.

All three services currently track `main` with auto-deploy enabled. A push to main can deploy: release approval must explicitly account for this before any push. No auto-deploy setting was changed. Preserve current start/build commands, environment, existing primary predeploy command `python run_migrations.py --only 20260901_os_repair_requests.sql`, and unrelated workers.

## Candidate contents — local patch only

Task base/HEAD is still `6e2805d058713cc64cfa70e7a85ee23ea66db7e1`. The current uncommitted source-repair scope to integrate onto a separately verified then-current production base is:

- `shopify_sync.py`, `shopify_order_financials.py`: financial projection/normalisation.
- Only `_upsert_order` and `save_meta_ads_sync` repair hunks in `supabase_backend.py`. **Exclude** the unrelated AI `create_dashboard_task` refactor in that same file.
- `meta_reporting_contract.py`, `meta_review_live.py`, `meta_review_sync.py`, `meta_review_store.py`, `ads_intelligence_page.py`: existing manual reporting path and metadata/filter repairs.
- `shopify_financial_repair.py`, `shopify_financial_canary.py`, `scripts/preview_order_financial_repair.py`, `scripts/check_source_read_access.py`, `scripts/render_source_preflight.py`: trusted diagnostic/planning and unwired canary modules. Review dependencies of the older app-importing access script before using it; the standalone Render probe is the tested remote path.
- Focused tests and source-repair documentation: `tests/test_source_data_repairs.py`, `tests/test_source_preflight.py`, `tests/test_shopify_financial_canary.py`, `tests/run_source_repair_checks.py`, and relevant Shopify/Meta fixture expectation changes.

Leave `os_ai/*`, AI UI/navigation, dashboard-task changes, worker AI-thread changes, AI caller refactors and the AI migration/manifest outside this **source-only** candidate. The local `os_ai/data.py` missing-source guidance belongs to the later AI release, not an excuse to include the whole subsystem. Current-base integration must preserve newer production edits and review conflicts at function level; file-copying the old backend is unsafe. Record a SHA only after an explicitly authorised candidate commit actually exists.

## Handler contract and test evidence

`prepare(ids, ledger, provider, contract)` produces a hashed schema-2 dry-run manifest for at most six explicit immutable GIDs. The manifest contains exact financial before-values, JSON key-presence/null flags, source/capture timestamps, protected row hashes and trigger/rule contract. Existing conflicting financial values or cancelled orders block preparation.

`apply` requires a **dedicated idle psycopg connection with dict rows**, an exact approval record, fresh OS provider data and the actual runtime revision. The operator's approval record must contain only `action`, `operation_hash`, sorted `order_ids`, `actor`, `approval_ref`, `release_sha`, `approved_at`, `expires_at`. This is a journal of trusted operator approval, **not an exposed authentication mechanism**. At deployment, compare the actual approved build to the service's real runtime revision; never insert a made-up SHA.

Execution is one transaction with advisory/row locks, 8-second statement and 3-second lock timeouts. It rechecks before-images and the database contract, changes only the six permitted financial values plus `updated_at`, verifies the protected data and inserts one scoped existing `audit_logs` event in the same commit. It does not call broad sync/edition functions or the generic audit helper's extra side effects. Other order fields and source/sync timestamps are not rewritten.

The enabled production `cancelled_edition_order_guard` was reviewed. It can force cancelled financial/workflow state in the NEW row; it has no external call in the order branch. Its function MD5 `023848686d5ca5aa31ede7286046835b` is an explicit reviewed allowlist entry. Changed/unknown functions, triggers or rules require review; the handler never disables them. Any unexpected post-write mutation rolls back. Operational release coordination must prevent concurrent schema/function changes.

Each operation hash has one ordered durable apply event and optionally one rollback event. A matching repeated request returns zero writes; conflicting/malformed history blocks execution. Connection/commit ambiguity raises `OutcomeUnknown` with no retry. Use **read-only `reconcile` on a fresh connection**; inspect its audit and state result before deciding anything. A confirmed rollback cannot reapply the same manifest.

`rollback` needs separate approval for action `rollback` and requires the complete audited after-image still to match. It restores only the old financial values and exact JSON key presence/SQL null roots; `updated_at` advances and the rollback audit remains. Later business changes block rollback rather than being overwritten. A partial failure in either direction rolls back the entire transaction, including the audit.

Focused command, credential-stripped subprocess and fixed disposable PostgreSQL 17.6:

```powershell
.\.venv-ai\Scripts\python.exe tests/run_source_repair_checks.py tests.test_shopify_financial_canary
```

**17 passed, zero skipped/failures/errors**, Python 3.14. Log: `.tmp-ai-verification/source-repair/canary-tests.log`.
Earlier this follow-up: `tests.test_source_preflight` **6 passed**.
An initial canary test exposed timestamp representation changing the manifest hash; canonical UTC formatting was fixed, then all 17 checks passed. This was a new local issue, not a production execution.

The previous 224 passes/34 pre-existing skips and isolated 11 Meta UI passes were not repeated because their implementation was unchanged. Their documented limitations and baseline weekly-reporting failure remain. A combined Python 3.12 test run on the eventual current-base candidate is still required. No production handler test is claimed.

## Private six-order evidence

Directory:
`C:\Dev\SportsCaveWorktrees\.studio\runtime\20261101-d2835a7c\source-repair-20261106\canary-preparation`.

Review `SIX_ORDER_CANARY_REVIEW.md` and `financial-canary-manifest.json`.
Current review hash: `7191100804903127c63153b8ded39ea34abbade7ba0e12f0e751cc726dbf646a`.
Provider capture 01:57:25 UTC and ledger capture 02:03:28 UTC on 6 November are separately timestamped. All six before-pairs remain blank; proposed total AUD 1,483.40. Five provider update timestamps advanced since the previous proposal. Same-input regeneration was identical.

These are **real read-only numerical records**, outside development preview; the transaction tests use independent **synthetic** IDs/data. The proposal neither proves whole-day/refund completeness nor authorises execution. The current review capture pair exceeds five minutes, so the handler deliberately rejects it for apply.

## Exact approval and rollout gates

1. **Candidate preparation gate:** approve a source-only current-base integration/review. No release SHA exists. Commit, push and production deployment each still require explicit authorisation; choose how to handle main auto-deploy before pushing. Preserve this task and unrelated work.
2. **Candidate acceptance:** on the exact integrated Python 3.12 candidate, run relevant source/canary/preflight tests, existing webhook/worker/startup regressions, synthetic full-app read-only smoke checks and topology validation. Check no sync executes on import/startup beyond existing authorised lifecycles. Confirm no new migration/dependency/secret/hosting requirement. Test production-compatible table constraints/RLS/role privileges in an appropriately secured environment.
3. **Release approval:** name the actual candidate SHA, all three service IDs, release window, current artifact IDs and recoverable production backup. Preserve AI flags `SPORTS_CAVE_AI_ENABLED=0`/`SPORTS_CAVE_AI_WORKER_ENABLED=0` and disabled policies; source-only release must not introduce the AI subsystem. Deploy the same approved build to all affected existing services; verify SHA, primary `/_stcore/health`, webhook `/healthz`, worker heartbeat/startup and normal read-only Orders/Ads/CRM/Edition access. No new webhook delivery or customer communication as a smoke test.
4. **Writer coordination:** the webhook's existing periodic reconciler can update these orders once the fixed writer is released. Do not manually trigger it. Refresh the six-row state before requesting any canary approval: if normal operation has already filled the pairs, skip those changes and revise the proposal. A temporary writer pause/resume is a separate consequential operational action needing explicit approval; none was performed.
5. **Shopify canary approval:** after all relevant writers use the fixed candidate, take a secure backup and fresh read-only six-ID provider/ledger/trigger captures, build the manifest and approve **that exact hash/IDs/before-after values**, permitted columns, actual release SHA, actor/reference, action `apply`, execution window/expiry and rollback policy. Finish within the five-minute source freshness bound or rebuild/reapprove. Recheck role privileges and related-table before-images. Only then may a trusted operator call the unwired handler. This document is not permission to call it.
6. **Post-apply acceptance:** reconcile one durable audit and exact six financial states, other two known orders, related edition/fulfilment/line/certificate state and unchanged source timestamps. Observe later ordinary reconciliation without forcing a resync. A failure or uncertain result must stop for read-only reconciliation. Rollback requires separately approved exact action and unchanged after-images.
7. **Meta gate, separate:** current access is good. Still prepare a complete GET-only account/day capture for 528975349337773, 5 November, AUD, Australia/Sydney; compare with Ads Manager under explicit `action_report_time=impression` and unified per-adset attribution. Retrieve/confirm the actual attribution settings and purchase definition; do not invent windows. Approve a row-set/hash, account/day scope and before-image backup before persistence through `sync_reporting`. No resync was executed here.
8. **Report acceptance:** after authorised source repair and full-day/refund reconciliation, explicitly regenerate a numerical Daily Brief. Cached historical reports remain immutable. Keep AI commentary, schedules and all live writes off until separately accepted/enabled.

## Rollback planning

Before commit, any failure aborts all financial writes/audit atomically. After commit, use the recorded audit to reconcile and, only with approval, perform field-scoped conditional rollback. Never restore a whole database or order record over newer work.

For a code rollback, record all three previous artifacts and their environment snapshots at release time. Returning to the old lightweight writer can erase repaired values again; do **not** assume code rollback protects data. Review a fixed-writer-compatible rollback or explicitly approve writer pause while resolving it. Coordinate Render auto-deploy and preserve the canonical primary. Database rollback, code rollback, worker pause and Meta restoration are separate approval scopes.

No production rollback, migration, deploy, backfill or resync has been run.
