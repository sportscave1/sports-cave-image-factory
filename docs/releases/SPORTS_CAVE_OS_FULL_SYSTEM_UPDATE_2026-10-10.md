# Sports Cave OS — Full System Update | October 2026

Date: 2026-10-10. **Status: RELEASE GATES PASSED; MIGRATIONS APPLIED; awaiting this commit's push and live verification.**

## Final resumed release

The user explicitly authorized one consolidated release. The existing checkout and 107-file inventory were reused. Fourteen newer original files were reconciled, preserving the release's Streamlit 1.65 compatibility and the original dirty workspace. No full-system audit or long benchmark was repeated.

- Fixed actual HTML loss: React Aria tabs activate on pointer-down, ahead of the existing click save guard. The guard now waits for acknowledgement before tab activation, serializes navigation and preserves keyboard navigation. Chrome and Edge verify exact HTML after rapid switching, sibling isolation, explicit save and fresh-page reopen.
- Fixed the 320px obstruction: the Campaign Home action popover remained open above the schedule dialog. Both timing dialogs dismiss only that Home menu. All 16 Home/detail cases pass across Chrome/Edge at 1440, 820, 390 and 320px, with countdown, confirmations, two intended synthetic operations and one page navigation. The first runner timed out after 11 passes; only five outstanding Edge cases were resumed.
- Reconciled worker repository adaptation, preparation publication fencing, consent verification cutoff, recipient-timezone revalidation, bounded acceptance retries and scheduled progress displays. Fixed a newly introduced local timedelta shadowing error in future-recipient polling.

## Targeted verification

89 affected campaign/editor SQL and UI tests passed on native local PostgreSQL; 12 independent-connection concurrency cases passed; a focused future-recipient polling test passed; two JavaScript navigation/refresh contracts passed. Existing passing Flow, catalogue and navigation evidence below remains applicable. Test data and transport were synthetic. No production email, campaign edit, reschedule, test send or cron invocation was performed.

Two reviewed additive migrations were applied to the authoritative Supabase project ceyzbfpuwuuxaiqwiltz: crm_flow_tests (20261010091448) and crm_campaign_preparation (20261010091509). No historical replay or data backfill. RLS and browser-role denial, immutable snapshot guards and publication fencing are verified separately after application. Render configuration and startup migration allowlists are unchanged.

The release includes the approved 107 paths plus this report, AGENTS.md and the new draft-navigation regression (109 changed files; the existing thumbnail UI check is byte-identical to main). Only these explicit paths are staged. Temporary results, database clusters, caches and secrets remain excluded. The original workspace and unfinished work remain preserved.

All four canonical services auto-deploy main. No Blueprint sync, new service or deployment duplication is needed. Post-push live SHA, health and startup results will be recorded in the local report after deployment. Authenticated production workflow verification requires an existing signed-in browser; current browser inventory has none. Local Chrome/Edge functional acceptance is complete; public live route/login checks do not prove authenticated data accuracy.

Local-only development remains the permanent default; this authorization is for this release alone.

## Retained evidence from the initial release preparation

The following is the historical pre-resume report. Its BLOCKED/not-applied statements describe the earlier safe stop and are superseded by the resumed release status above.

# Sports Cave OS — Full System Update | October 2026

Date: 2026-10-10. **Status: BLOCKED BEFORE COMMIT, PUSH, DATABASE MIGRATION AND DEPLOYMENT.**

## Release outcome

No new commit exists and nothing was newly deployed by this task. GitHub main and the four existing Render services remain on `ae3baaeb55a42710edf9518443dac582544a7c5c`, the earlier release. Production/customer/Shopify/edition data was not modified. No email, publication, pause, test send, cron run or live campaign amendment occurred.

The isolated consolidated checkout is `.tmp-full-system-release`, branch `codex/full-system-update-2026-10-10`, based on current main. Original local changes, historical branches, archives and supporting worktrees remain preserved. No reset, stash, force push or original source overwrite was used. This report and the requested local-only policy are new local documentation. Permanent local-only development mode is restored in AGENTS.md; future release operations require explicit authorization.

## Critical unresolved gates — safe stop

1. **Draft preservation during navigation is unverified.** A synthetic Chrome check fills the first editor HTML textarea, immediately opens Settings, selects Email 2 and reads the synthetic automation records. The marker is absent from all records; all retain revision 2. The same check fails against the original local source. This does not establish the underlying cause or prove that consolidation introduced a regression, but persistence must be established before release. No real customer/email was involved. Evidence: `.tmp-full-system-audit/flow-flush.log`, `flow-flush-original.log`, `check-flow-flush.cjs`, `run-flow-flush.py`.
2. **320px Campaign Home acceptance fails.** Chrome detail passes at 1440, 820, 390 and 320px. Chrome Home passes at 1440, 820 and 390px. At 320px a floating overlay intercepts pointer events on a campaign control. Remaining Edge cases do not execute after that failure. Harness versus UI cause remains unresolved. Evidence: `.tmp-full-system-audit/merged-campaign-browser.log` and campaign fixture logs. Full browser acceptance is not claimed.
3. **Original source changed during the audit.** The final comparison against the initial source snapshot found 14 changed original candidate files, including campaign logic and the preparation migration. No original application source was edited by this release task. These latest contents are not fully reconciled or validated in the isolated release, so the proposed release is not a complete current snapshot. Both current files and the initial snapshot are preserved. Evidence: `.tmp-full-system-audit/original-preservation-check.json`.

The user's mandatory instruction to stop when critical issues remain applies. No partial release was staged or pushed and no production schema changes were applied. The remaining steps are reconcile the newer files, diagnose the draft-preservation and narrow-screen failures, validate the final source, then seek explicit authorization for a resumed release.

## Audit and Git reconciliation

Original HEAD: `b526c1d`, divergent from remote. Merge base: `7c5896ae463ea36d58ead73000a544011e0d7e35`. GitHub main was fetched and rechecked with ls-remote; it remains `ae3baaeb55a42710edf9518443dac582544a7c5c`. The four contents from the unique original commit were already represented in main.

233 eligible source/report records were compared: 124 already live, 88 local updates, 7 clean three-way merges, 7 conflicts and 7 new-file collisions. Shared files were reconciled in the isolated checkout against current main so previously deployed changes were retained. The initial candidate release contains 107 source, migration, test and report files. This excludes this report and AGENTS.md policy. It is a candidate inventory, not a deployed file count. Final hashes are in `.tmp-full-system-audit/pending-release-files.json`.

## Proposed updates, not newly live

- Automations V5: fragment routing, history/latest-click behavior, unsaved-route restoration, memoized reads/definitions, bounded refresh and lazy settings.
- Flow V5: lazy recipient/checkout/period reads, compact toolbar and gated internal whole-flow test UI/worker processing with isolated test tables.
- Campaign V7/V7.1/V8: durable review acceptance/background preparation, explicit timezone and recipient-local/DST handling, revision-checked/idempotent future schedule amendments, worker coordination, shared schedule/Send Now dialogs, countdown and compact Home/progress.
- Catalogue picker: stable IDs for duplicate titles, selection retention, keyboard/focus and cancel/save behavior. A consolidation fix scopes the V6 editor navigation guard so catalogue options are not intercepted as navigation.
- Presentation: compact Fulfilment and diagnostic-route handling in page_presentation.py/os_pages.py. Whole-application workflow completion is not claimed.
- Associated targeted tests, synthetic fixtures, benchmarks and historical implementation reports.

## Already live and preserved

Current main already contains Email Editor V6 runtime/draft/source protections; earlier Navigation V4/V5 changes; Flow V4/thumbnail work; Meta Review V3; Table Design V3; Design Studio V3; premium glass presentation; Orders, Editions/certificates; Mockups/Product Upload; Social Media/Wall Preview inbox; design tracking; health, migrations and worker supervision. These were compared against current source rather than counted again as newly live.

The V6 archive SHA-256 is `b90c194ad876d87986ec18eb2e39b51680a7328bfc62541a6a39677d299d96e7`. Its runtime is already represented in main; composer/section UI comparisons normalize CRLF. The automation-live-stages worktree's V6 runtime is already live. Prior release and premium-image worktrees are clean ancestors of main. June backup/revert history is superseded and was not included.

## Verification completed and limitations

- **162 campaign tests passed on native local PostgreSQL 17.6, no skips.** Nine independent-session concurrency cases include edit versus worker, Send Now/outage/retry, duplicate operation, rollback, postponement/activation and competing admin revisions. Log: `native-campaign-gate.log`.
- Initial merged SQL/unit gate: **106/107 passed**. The obsolete Draft display-label failure was resolved by restoring final V5 display labels; **all 23 affected Flow V4/V5 cases then passed**. Immutable LIVE/source-loader behavior was preserved. Logs: `merged-sql-unit.log`, `final-flow-recheck.log`.
- **Four catalogue picker journeys passed**, main and edge cases in Chrome 1440px and Edge 320px on Streamlit 1.65: duplicate IDs, selection persistence, pagination, missing collections, limits, cancel/focus, keyboard and Escape. Log: `merged-picker-browser.log`.
- **14 navigation fault checks passed on Streamlit 1.65**, including latest/stale route handling, browser history, delayed SQL, identity/definition failures and failed-save URL preservation. Log: `merged-navigation-165-browser.log`.
- V6 source contracts passed in Chrome/Edge; **29 incremental JavaScript/server composition checks** and **eight keyboard/menu/focus scenarios** passed. Refresh serialization, acknowledgement, terminal/unmount, hidden-listbox and navigation-ready contracts passed.
- Selected release Python files parse successfully; the earlier whole-release AST gate passed. Render topology validator passed: the canonical primary service remains externally managed and the Blueprint owns one webhook service. No render.yaml change or Blueprint sync occurred.
- Existing valid evidence was reused for unchanged code. The long 578-case gate and performance matrices were not repeated. Local fixture timings are not certified production performance. One prior frozen-discount assertion conflicts with the already-live current-LIVE policy; no delivery policy was changed to satisfy it.
- Browser failures and newer original files prevent final release signoff. Populated app-wide workflows, secondary dialogs/accessibility, geography edge cases and live performance targets remain limited or unverified. Internal flow testing requires configured allowlists/isolation gates; no test email was sent.

## Database safety and rollout requirements

Supabase inspection was read-only. Existing campaign/runtime tables and RLS were inspected; preparation and flow-test tables are absent. The proposed additive migrations `20261010090000_crm_flow_tests.sql` and `20261010110000_crm_campaign_preparation.sql` have **not** been applied. They introduce server-only internal tables and immutable guards, without customer/order/edition backfill. Their latest changed contents must be reconciled and reviewed again before execution.

Existing migration allowlists and Render configuration remain unchanged. Main and worker timing implementations must run the same release before amendments are used; mixed-version activation must be addressed during rollout. No historical migration replay, customer mutation or production data sample was performed. Local SQL/browser fixtures used synthetic records and blocked external requests.

## Excluded work

Temporary images, generated screenshots/JSON browser evidence, caches, .venv/node_modules, secrets/.env, local database clusters, unrelated files, generated regression output and manual deployment ZIP/PowerShell packages are excluded and preserved. Incomplete workflow acceptance and production performance claims are not described as completed work. The suspended legacy Render service was untouched. The original dirty working tree and supporting worktrees were not reset, overwritten or deleted.

## Render status at safe stop

All latest deployments were rechecked through the confirmed Nathan workspace.

| Service | Deployment | Status | Commit |
|---|---|---|---|
| sports-cave-os | dep-db4q0rn40ujc73brh0n0 | live, prior release | ae3baaeb55a42710edf9518443dac582544a7c5c |
| sports-cave-os-webhooks | dep-db4q0rv40ujc73brh1vg | live, prior release | same |
| sports-cave-seo-worker | dep-db4q0rv40ujc73brh270 | live, prior release | same |
| sports-cave-seo-daily-sync | dep-db4q0rv40ujc73brh2i0 | live, prior release | same |

No new service, deployment trigger, Blueprint sync or cron invocation occurred. No new-release health verification can be claimed because this release was not committed or deployed.

## Original files changed during audit

- `crm_campaign_home.py`
- `crm_campaign_home_progress.py`
- `crm_campaign_progress.py`
- `crm_campaign_progress_ui.py`
- `crm_campaign_schedule.py`
- `crm_campaign_send.py`
- `crm_campaign_send_ui.py`
- `crm_worker.py`
- `migrations/20261010110000_crm_campaign_preparation.sql`
- `tests/check_campaign_hardening_browser.py`
- `tests/fixtures/campaign_hardening_preview.py`
- `tests/test_campaign_hardening.py`
- `tests/test_campaign_hardening_concurrency.py`
- `tests/test_crm_campaign_preparation.py`

## Full proposed file list

- `app.py`
- `components/crm_sections/automation_navigation.js`
- `components/crm_sections/automation_refresh.js`
- `components/crm_sections/composer.js`
- `components/sports_cave_top_bar/index.html`
- `crm_automation_home.py`
- `crm_automation_read_cache.py`
- `crm_automation_store.py`
- `crm_automation_toolbar.py`
- `crm_automation_ui.py`
- `crm_campaign_controls.py`
- `crm_campaign_countdown.py`
- `crm_campaign_delete.py`
- `crm_campaign_home.py`
- `crm_campaign_home_data.py`
- `crm_campaign_home_progress.py`
- `crm_campaign_page.py`
- `crm_campaign_preparation.py`
- `crm_campaign_progress.py`
- `crm_campaign_progress_ui.py`
- `crm_campaign_schedule.py`
- `crm_campaign_send.py`
- `crm_campaign_send_ui.py`
- `crm_campaign_snapshot.py`
- `crm_campaign_store.py`
- `crm_campaign_timing_ui.py`
- `crm_email_diagnostics.py`
- `crm_engine.py`
- `crm_flow_page.py`
- `crm_flow_test_ui.py`
- `crm_flow_tests.py`
- `crm_flow_thumbnail.py`
- `crm_page.py`
- `crm_section_ui.py`
- `crm_worker.py`
- `docs/AUTOMATIONS_FLOW_V5_TOOLBAR_TEST_AND_CHECKOUTS.md`
- `docs/AUTOMATIONS_V5_INSTANT_NAVIGATION_PERFORMANCE.md`
- `docs/CAMPAIGNS_V7_1_PREMIUM_UI_SCHEDULE_MANAGEMENT.md`
- `docs/CAMPAIGN_CATALOGUE_COLLECTION_PICKER_FIX.md`
- `docs/CAMPAIGN_SCHEDULING_V8_RELIABILITY_TIMEZONE_REPAIR.md`
- `docs/SPORTS_CAVE_OS_APPWIDE_UI_UX_V1.md`
- `migrations/20261010090000_crm_flow_tests.sql`
- `migrations/20261010110000_crm_campaign_preparation.sql`
- `os_pages.py`
- `page_presentation.py`
- `scripts/benchmark_appwide_ui_v1.py`
- `scripts/benchmark_automations_v5.py`
- `scripts/benchmark_flow_v5.py`
- `scripts/inventory_appwide_ui_v1.py`
- `scripts/summarize_automations_v5.py`
- `tests/benchmark_campaign_acceptance.py`
- `tests/benchmark_campaign_hardening.py`
- `tests/benchmark_campaign_v7_1.py`
- `tests/campaign_real_postgres.py`
- `tests/check_automations_v5.py`
- `tests/check_automations_v5_faults.py`
- `tests/check_automations_v5_overview_paint.py`
- `tests/check_campaign_hardening_browser.py`
- `tests/check_campaign_hardening_layout.py`
- `tests/check_campaign_v8_ui.py`
- `tests/check_crm_collection_picker_browser.py`
- `tests/check_crm_collection_picker_edges.py`
- `tests/check_crm_flow_v4_operations.py`
- `tests/check_crm_flow_v4_ui.py`
- `tests/check_crm_flow_v5_ui.py`
- `tests/check_crm_thumbnail_ui.py`
- `tests/crm_postgres_server.mjs`
- `tests/fixtures/appwide_ui_v1_preview.py`
- `tests/fixtures/appwide_ui_v1_survey.py`
- `tests/fixtures/automation_v5_paint.js`
- `tests/fixtures/automation_v5_routed.py`
- `tests/fixtures/automation_v5_sql.py`
- `tests/fixtures/campaign_hardening_preview.py`
- `tests/fixtures/campaign_v7_1_preview.py`
- `tests/fixtures/campaign_v8_preview.py`
- `tests/fixtures/crm_collection_picker.py`
- `tests/fixtures/crm_flow_v5_preview.py`
- `tests/fixtures/crm_send_progress_preview.py`
- `tests/fixtures/flow_v4_regression.py`
- `tests/run_campaign_hardening_regression.py`
- `tests/test_appwide_ui_v1.py`
- `tests/test_automations_v5.py`
- `tests/test_campaign_hardening.py`
- `tests/test_campaign_hardening_concurrency.py`
- `tests/test_campaign_leave_dialog.py`
- `tests/test_crm_automation_hidden_listbox.cjs`
- `tests/test_crm_automation_loading.py`
- `tests/test_crm_automation_navigation.py`
- `tests/test_crm_automation_publication.py`
- `tests/test_crm_automation_refresh_controller.cjs`
- `tests/test_crm_automation_stability.py`
- `tests/test_crm_campaign_preparation.py`
- `tests/test_crm_campaign_sections.py`
- `tests/test_crm_campaign_v2.py`
- `tests/test_crm_campaign_v7_1.py`
- `tests/test_crm_campaign_v8.py`
- `tests/test_crm_campaign_v8_performance.py`
- `tests/test_crm_flow_settings_removed.py`
- `tests/test_crm_flow_v4.py`
- `tests/test_crm_flow_v5.py`
- `tests/test_crm_home_live_progress.py`
- `tests/test_crm_picker_selection.py`
- `tests/test_crm_postgres.py`
- `tests/test_crm_production_unsubscribe.py`
- `tests/test_crm_production_v2.py`
- `tests/test_crm_send_progress.py`
- `tests/test_crm_thumbnail_cache.py`
