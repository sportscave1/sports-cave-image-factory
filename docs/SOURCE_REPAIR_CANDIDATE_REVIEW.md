# Source-only candidate review — 6 November 2026

Task `20261106-source-repair`; owner `codex-source-release-20261106`. Isolated Studio home `C:/Dev/SportsCaveWorktrees/source-repair-release-studio`. Branch `codex/task/release-source-repair-release-candidate-20261106-source-repair`.

All three live Render revisions rechecked: `64ed998a7e5f26fefd2d559fc2d7bb1873e24832`. This is the candidate base, NOT a new candidate SHA. No commit exists. Source task remains untouched, including its uncommitted AI work; prior follow-up file hashes were checked unchanged.

## Integrated scope

Financial query/pair preservation and Meta filter/reporting/metadata repairs applied cleanly as a patch onto production; no merge conflicts. The backend patch includes only `_upsert_order` and `save_meta_ads_sync`. Added financial validation, reporting contract, read-only diagnostics/dry-run scripts and unwired financial canary handler with their focused tests. Existing dependencies and tables suffice; no dependency upgrade or migration.

Excluded: `os_ai`, AI navigation/callers/worker/migration, dashboard-task refactor and AI reader guidance. App, worker, migration runner, account permissions and render.yaml equal the production base. The one test importing the excluded AI BusinessTools reader is omitted from this source-only suite; its prior passing evidence remains in the original worktree. No source-repair coverage is represented as new AI acceptance.

## Verification

Combined candidate suite: **279 run, 245 passed, 34 existing retired-allocator skips, zero failures/errors**, Python 3.14 / native disposable PostgreSQL 17.6. Modules: source_data_repairs, shopify_financial_canary, source_preflight, shopify_sync, Meta SyncTests/live reads/normalization/cache/v3, Ads Intelligence, sports_cave_worker and webhook_health_responsiveness. Credentials stripped and AI flags off by tests/run_source_repair_checks.py. Webhook requests were synthetic TestClient calls, not real deliveries. No preview or live data loaded.

Topology and whitespace checks pass. Prior GraphQL schema validation, isolated Meta UI tests, source defect reproductions and successful real credential preflight are reused; provider preflight was not rerun. Existing weekly-reporting assertion baseline remains unrelated and unchanged. The independent Python 3.12 result below completes the runtime gate; full-app browser smoke acceptance remains a release gate.

Evidence outside Git: `../.studio/runtime/20261106-source-repair/candidate-tests.log`, `candidate.patch`, `candidate-files.json`. The patch includes new files without staging or committing. Hash manifest identifies the reviewed file contents, not a Git candidate SHA.

The same combined suite also passed in a disposable local Python **3.12** container: **279 run, 245 passed, 34 skips**, zero failures/errors. Candidate mount was read-only; credentials removed, AI off; only the synthetic loopback database address was mapped to Docker's host address. Evidence: `python312.log`. This completes the runtime gate mentioned above. Full-app browser smoke on the eventual committed build remains pending; no live credentials are needed for it.

## Exact service scope and rollback artifacts

| Existing service | ID | Current rollback artifact | Scope |
|---|---|---|---|
| sports-cave-os | srv-d8kl4on7f7vs73dvavv0 | dep-dbmegs95efls73e3trrg | Order backend and manual Ads Sync Performance |
| sports-cave-os-webhooks | srv-d9146onlk1mc739nrm7g | dep-dblcdgm7bikc73ah4l1g | Active periodic order reconciliation and webhook writer |
| sports-cave-seo-worker | srv-d9ujm9navr4c73amurgg | dep-dblcdgm7bikc73ah4kjg | Shared backend/Shopify dependencies; coordinated compatibility release |

Keep existing commands, primary identity, environments and suspended SEO cron unchanged. No hosting services/costs added. All three track main with auto-deploy: a future push must account for that. No AI feature or automation is introduced or enabled by this patch.

Before release: finish full-app browser candidate acceptance, verify production backup/role privileges, explicitly approve the real committed SHA and all three existing services. Primary health `/_stcore/health`, webhook `/healthz`, worker startup and ordinary read-only business pages must pass. Do not trigger resync or customer sends as smoke tests.

If release fails, stop and assess all three artifacts/environment snapshots. Reverting to the defective old writer can erase repaired amounts: coordinate a separately authorised writer pause or fixed-writer-compatible rollback. Never restore the whole database over later business writes. Data rollback is separate: reconcile durable canary audit, require unchanged after-images and exact rollback approval. Meta restoration needs its own scoped before-image review.

The existing periodic webhook writer may naturally repair the six orders after eventual release. Re-read before preparing a canary; skip already repaired rows. Current six-order manifest is stale by design and cannot authorise execution. Meta complete-day/attribution reconciliation and real Daily Brief acceptance remain pending. See SOURCE_DATA_CANARY_PREPARATION.md for handler, protection and separate canary gates; its earlier unintegrated status is superseded by this review.

## Next approval

Review this uncommitted source-only diff. Commit-only approval may establish a candidate SHA; it does not authorise push or release. Production approval must wait for remaining runtime/preview acceptance and name that actual SHA, the three services, backup and rollback window. Shopify/Meta canaries, backfill/resync and AI activation remain separate and unauthorised.

No commit, push, deploy, production write, canary, backfill, resync, new paid service or AI activation occurred.
