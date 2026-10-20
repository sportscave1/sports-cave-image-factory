# SEO Worker Phase 1 — local implementation and review notes

Task: `20261020-57995487`, owner `seo-phase1-20261020-01a156b4`.
Worktree: `C:\Dev\SportsCaveWorktrees\sports-cave-growth-seo-worker-phase-1-consolidated-workspace-20261020-57995487`.
Branch: `codex/task/growth-seo-worker-phase-1-consolidated-workspace-20261020-57995487`.
Approved Studio base: `59b609728b182c6c997f02ed0a8786fff0483095`.
The supplied category folder was clean and idle; Studio allocated this separate task. The original repository and other task/recorder work were not edited. Changes are uncommitted. No deployment, migration, worker activation, Shopify publication, email or ad action was performed.

## Bounded inventory and migration map

| Existing feature / ID | Reused implementation / records | New destination and compatibility |
|---|---|---|
| SEO Overview / `seo` | Google direct reporting, SEO connection diagnostics | Worker is the default; performance is Analytics. Existing root ID remains valid. |
| Keywords & Rankings / `seo_keywords` | `GoogleReports.gsc`, source positions and query/page/date details | Analytics → Queries; old ID opens that view. |
| SEO Landing Pages / `seo_landing_pages` | GSC page rows, GA4 landing-page contract | Analytics → Pages; conversion context is separate, avoiding an incompatible URL join. |
| Keyword Mapping / `seo_keyword_mapping` | Existing keyword library, GSC CSV importer, mapping editor, state collection | Analytics → Mappings plus query details; all mapping IDs remain unchanged. |
| Opportunities / `seo_opportunities` | Existing observed-evidence scoring, keyword and saved recommendation records | Plan; Analytics creates persistent tasks with query, target, range and filter evidence. Worker evaluates at most 500 loaded rows. |
| SEO Health & Fixes / `seo_health` | Saved technical audits, existing inspection/recheck and admin tools | Plan → Technical fix, import saved findings; manual audit tools stay reachable. No crawler is started locally. |
| SEO Blog / `seo_blog` | Existing v2 brief/CSV/research/image/prompt editor; existing JSON blog builder, assets, pack exports | Review → Blog projects for the old route. Saved drafts remain independently editable, with links from Plan. |
| Reports & Strategy, Tasks & Results | Existing growth reports, recommendations, tasks and measurements | Plan adapters and existing manual task tool; saved proposals in Review. Original IDs/statuses are retained as references. |
| Citations / internal links / outreach | Existing editors and repositories | Plan → Existing manual tools; old aliases remain valid. |
| Analytics Overview / `analytics` | GA4 totals, comparisons, trend, dimensions; separate Shopify order ledger | Analytics → Channels, Overview details, Audience, Store operations. All-channel scope retained. |
| Traffic & Acquisition / `analytics_traffic` | Canonical traffic-acquisition contract | Analytics → Channels, default all-channel scope. |
| Pages & Engagement / `analytics_pages` | Pages/screens, landing-page and event contracts | Analytics → Engagement, Pages and Events. |
| Analytics Ecommerce / `analytics_ecommerce` | Canonical item ecommerce contract | Analytics → Ecommerce. Attributed purchase revenue and Shopify sales remain separate. |
| Analytics Realtime / `analytics_realtime` | Canonical realtime contract | Analytics → Realtime; visibly last 30 minutes, all channels, independent of date/scope controls. |

The only visible SEO children are Worker, Analytics, Plan, Review and History, in that order. The old top-level Analytics disclosure was removed. Old route names, page keys and permission entries remain registered for saved links. Existing Analytics-only accounts can reach the consolidated GA4 workspace without gaining GSC, mapping or Plan access. Campaign ownership stays with Ads. Shared Google APIs/contracts were not changed, preserving other consumers.

## Working behavior

- One reporting entry point, existing single-flight bounded Google memory cache and canonical GA4 contract execution. Google organic is the GA4 default; all organic and all channels remain explicit alternatives.
- Complete 28-day default ending no later than three Pacific days ago and bounded by the available final GSC watermark. Seven days, 90 days, custom dates and previous-period comparison work. Empty/missing values stay unavailable. Custom recent periods are flagged.
- Five primary metrics; one selectable chart; Pages/Queries/Channels and additional GA4 capabilities through one View selector. Source diagnostics expose quality, fetched time, currency and timezone. Source failure preserves same-filter results independently. UI fallback caches are bounded and scoped by user, connection and filters.
- Query/page/date reports retain source grain; conversions are never duplicated into query rows. GA4 landing-page conversions remain a separate source table. URL identity is preserved; task deduplication uses the existing technical-audit URL normalizer, which removes known tracking parameters and preserves meaningful ones.
- Low-CTR, position 11–20, declining clicks and GA4 sessions/no-recorded-purchases signals have explicit thresholds and unavailable states. No invented query revenue, search volume, difficulty, forecast or purchase-session rate.
- Persistent manual task creation, edit, priority, defer/dismiss statuses, linked draft creation, deduplication by target/query/type/intent, evidence and range/filter context. Different issues on one URL remain separate. Saved work adapters retain source references, and unapproved legacy growth tasks remain admin-only.
- Both existing blog editors remain available. The v2 editor has an additive local project-store adapter for safe manual testing. Draft/project review decisions record a content revision; edits invalidate the prior decision. Approval has no publishing effect.
- Local History records actual task, mapping, draft, scan and review actions. A refresh event means cache invalidation, not a successful sync or fix. Shared mode additionally reads existing SEO audit, sync and owner-scoped Blog project history; missing history is reported honestly.
- Worker shows available source state, evidence dates, actual Plan/review counts, next tasks, recent events and Settings. Its bounded operation evaluates loaded evidence and saves/deduplicates tasks. It does not claim a durable runner.

## Local execution boundary

`seo_phase1.local_mode()` defaults to local. New persistence uses `.local/seo-phase1.json`; local v2 projects share that JSON store. Existing local editor activity is routed into the same local history instead of the global audit logger. Local mapping intelligence does not discover shared database configuration. Shared datasets are not copied into the fixture.

`SEO_PHASE1_MODE=shared` is an explicit integration hook for a later authorized environment. Do not enable it in a development preview pointed at production: existing shared stores can prepare their schemas and existing admin tools retain their original capabilities. This task never enabled that mode. This is an SEO workspace boundary, not an application-wide sandbox for Orders/Ads/Email or the production server launcher.

The full `sports_cave_server.py` was not started. The separate fixture imports the SEO UI directly, injects synthetic reporting and local storage, and does not start app workers or deployment migrations. Automated UI checks deny external requests and database connections and assert zero calls.

## Recorder / companion / Codex handoff

Verified recorder implementation: `components/sports_cave_top_bar/index.html` uses `getDisplayMedia` and `MediaRecorder`, then downloads a WebM. It does not create a durable SEO execution session or replay contract. The existing recorder remains untouched in shared tooling.

Verified companion: `scripts/studio/companion.py` supervises a task/owner-bound Developer Studio worker, local pairing, draft UI and recovery. That is not an SEO job dispatcher. No SEO adapter or fake Start control was added.

Smallest future handoff proposal (documentation only):

```json
{
  "version": 1,
  "task_id": "existing stable Plan ID",
  "target": {"entity_type": "page or draft", "id_or_url": "existing identity"},
  "proposal_revision": "content hash",
  "evidence": {"source": "GSC or GA4", "date_range": {}, "filters": {}},
  "permitted_scope": ["prepare local proposal"],
  "attachments": [],
  "recorder_session_ref": null,
  "companion_session_ref": null
}
```

Missing capability: an authenticated, owner-bound SEO execution dispatcher with durable acknowledgement, idempotency, permitted-action checks, cancellation/recovery and result references. Recorded/web content is evidence only; it cannot expand authority. Publishing requires separate explicit authorization and the existing publishing permissions.

## Files changed by purpose

- Navigation / access: `seo_navigation.py`, `app.py`, `os_accounts.py`.
- Consolidated entry points / editor safety: `seo_page.py`, `analytics_page.py`.
- Additive state / queue / history / local blog adapter: `seo_workspace.py`, `seo_phase1.py`.
- Five-page UI and report adapters: `seo_phase1_ui.py`.
- Offline verification: `tests/test_seo_phase1.py`, `tests/test_seo_phase1_ui.py`, `tests/fixtures/seo_phase1_preview.py`; legacy navigation expectations updated in three existing test modules.
- Local artifact exclusion: `.gitignore`; this review document.

Inactive reporting helpers remain in the existing modules because older regression tests and manual analysis helpers reference them. Both public reporting entry points now delegate to the same workspace. Further removal should migrate those source-inspection tests together; there is no second visible reporting implementation.

## Verification

Python 3.14 lacked pytest, psycopg, cryptography and dotenv in its default environment. Test-only dependencies were installed into ignored `.local/python-deps`; no application dependency manifest was changed. Playwright was installed into ignored `.local/browser-tools`, using the already installed headless Chromium executable.

- New model and offline UI tests: **15 passed**. Covers menu, permissions, compatible scopes, CTR, missing values, URL/intent deduplication, reload persistence, revision invalidation, health issue identity, local DB isolation, project event idempotency, all report views, partial failure, task→draft→review→history and existing v2 editor startup.
- Combined focused suite: **133 passed, 5 failed, 6 subtests passed**. All five failures reproduce against original files extracted from approved HEAD: the Files-sidebar source assertion; analytics refresh stage/source queue expectations despite existing disabled refresh; old Refresh analytics button count; top-bar loader exact source-string expectation. No changed runtime source in those baseline behaviors.
- Additional account/access/sidebar/navigation suite: **103 passed, 5 failed, 6 subtests passed**. Its five failures also reproduce on approved HEAD with the same assertions: old Password Access label, blanket admin access despite Developer Studio owner restriction, old Files detail request, product prompt button count and Adobe Photoshop preview label.
- Python compilation of touched application modules: passed.
- `python scripts/validate_render_topology.py`: passed. No Render configuration change or Blueprint sync was performed.
- Headless fixture screenshots at 1440px, 1920px and 1280px with CSS zoom 1.25: document scroll width equals viewport width, no Streamlit exceptions. This is the isolated SEO fixture, not full authenticated app chrome. Browser zoom was simulated with CSS zoom.
- Live GA4/GSC reconciliation and shared Postgres reads/writes were intentionally not exercised. Offline tests verify contracts and source scopes, not production values.

The combined command lists these modules under `tests/`: `test_seo_phase1`, `test_seo_phase1_ui`, `test_seo_blog_workflow`, `test_seo_blog_streamlit_lifecycle`, `test_seo_technical_audit`, `test_analytics_fragment_reads`, `test_analytics_contracts`, `test_google_direct_reporting`, `test_seo_metrics_v2`, `test_analytics_navigation`, `test_seo_workspace`, `test_seo_live_analytics`, `test_seo_performance_repair` (all `.py`). Run with `python -m pytest ... -q` and `.local/python-deps` on `PYTHONPATH`.

## Open and exercise locally

From the task worktree:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) '.local/python-deps'
$env:SEO_PHASE1_MODE = 'local'
python -m streamlit run tests/fixtures/seo_phase1_preview.py --server.address 127.0.0.1 --server.port 8876
```

The fixture is explicitly labelled synthetic. Open `http://127.0.0.1:8876`, choose Analytics → Queries, inspect a row and create a Plan task. In Plan prepare its linked draft; in Review use Saved drafts or Blog projects, save a revision and an internal decision. Open History, then Worker and evaluate the loaded evidence. Reload and confirm saved records persist under `.local/fixture/workspace.json`.

## Concrete remaining work

1. Shared-data integration requires an isolated development database copy and approved read-only integration access. Verify existing datasets/permissions, field-grain comparisons and cross-module navigation there before enabling shared mode. No production migration is needed for the local JSON implementation; shared JSON payload additions are additive.
2. Existing growth tasks/proposals remain owned by their original workflows. Plan adapters link them; editing the wrapper does not synchronize all legacy source statuses bidirectionally. Use the preserved source tool for those actions. A later narrow adapter can add explicit source status updates against a development copy.
3. Shared History merges existing audit, sync and owner-scoped Blog project events. Verifying these adapters against development records remains a follow-up. Do not interpret a sync as execution.
4. App-wide authenticated preview and real browser 125% zoom remain separate from the isolated fixture checks. No full-app claim is made.
5. Durable automation, proposal generation, recorder replay and companion/Codex execution are future capabilities. Phase 1 provides manual preparation and a bounded evidence scan only.
