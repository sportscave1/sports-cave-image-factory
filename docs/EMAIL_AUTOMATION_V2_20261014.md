# Email Automation V2 — local implementation and review

14 October 2026. Task `20261011-54d8ff88`, owner `me/email-flow-fix`. Baseline: Unified V1 at `226f6d378bc0a470a8e4fbe63491287e2588c1a4`. Changes remain uncommitted in the assigned worktree. No push, deployment, live enrollment, activation, live schedule change or real email was performed.

## Implemented

- Preserved the Checkout master table, its 34 px rows, sticky headings/customer columns, colours, guarded operations and V1 adapters. All five flows still use the same recipient shell, state/read layer, table, workspace and editor.
- Shared pagination now uses native callbacks: one fragment execution and one page read per click, instead of rendering the old page and explicitly rerunning again. Lifecycle pagination now has the same compact placement and verified page/row counts as Checkout. Counts describe the visible page, not an invented audience total.
- Added immediate, accessible visible-row and cross-page selection counts; detail toggle state; shared Close details; Escape dismissal within the table; keyboard focus restoration by record identity when rows change. Duplicate customer names cannot move focus to another order.
- Fixed two reproduced navigation defects: expanded panels closed on flow switches, and filters could revert if navigation occurred before a slow query completed. Open/closed state now lives outside disposable widget state; input is checkpointed before reads.
- Kept guarded action buttons present and disabled during initial loading. Moved Checkout's off-page-selection explanation into the action tooltip so selection does not insert a row above the table. Active date filters have a visible outline.
- Updated shared workspace styles for current React Aria controls as well as the older BaseWeb hosts. Reporting, timing and editor-entry controls align at 32 px; compact stage statuses no longer truncate “DRAFT”. Desktop/mobile visual checks retained the existing Sports Cave identity.
- Added one shared sequence label distinguishing draft editing from publication. Published sequence contents, immutable journey steps and receipt-derived status remain separate and unchanged.
- Checkout now honours the shared 150 ms bounded read allowance; its old 50 ms override caused avoidable settlement round-trips. Removed expired/disconnected settlement timer registry entries. No new dependency, framework, SQL change or migration was needed.

## Shared ownership and retained differences

`crm_flow_recipients.py` owns disclosure retention, filtering checkpoints, selection/event fencing, table dispatch, read settlement, detail closing and pagination. `components/crm_checkout_table/index.html` owns all browser table interactions. Existing `crm_flow_page.py`, composer and sequence operations remain shared.

| Flow | Necessary source/operation differences retained |
|---|---|
| Abandoned Checkout | Incomplete checkouts, recovery/countdowns, keyset pagination, repair and guarded page-scoped enrollment requests |
| Welcome Series | Subscriber/consent facts and existing subscription timing |
| Post Purchase | Order-first audience, payment/fulfilment facts, administrator-confirmed Add to Flow and existing fallback controls |
| Win Back | Inactivity audience, purchase history and existing timing rules |
| Fulfilment Follow-up | Read-only recorded enrollment history; no inferred audience or historical backfill |

No marketing consent, suppression, unsubscribe, deduplication, payment verification, scheduler, publication or send-history authority changed.

## Performance evidence

Three-sample medians in milliseconds, Chromium at 1440 px, real Streamlit fragments, fresh sessions with 50 visible rows and running servers. Synthetic sources delay reads by 20 ms; the fuller Post Purchase row uses disposable PostgreSQL. Browser readiness is observed when the iframe is visible and contains its rows. Fixture initialization is excluded and reported separately. Raw samples and the more conservative Playwright wait timings are in `email-automation-v2-evidence.json`.

| Flow | Cold browser readiness V1 → V2 | Warm browser readiness V1 → V2 | V2 cold / warm Streamlit body | V2 component initial render |
|---|---:|---:|---:|---:|
| Abandoned Checkout | 230 → 265 | 158 → 146 | 29.81 / 6.67 | 5.0 |
| Welcome Series | 221 → 246 | 161 → 183 | 30.36 / 7.28 | 11.7 |
| Post Purchase | 244 → 232 | 177 → 180 | 30.19 / 8.86 | 9.5 |
| Win Back | 269 → 241 | 162 → 202 | 30.24 / 7.01 | 12.3 |
| Fulfilment Follow-up | 252 → 244 | 146 → 167 | 28.94 / 7.28 | 8.1 |
| Post Purchase, fuller SQL fixture | 270 → 269 | 203 → 190 | 27.39 / 10.39 | 12.5 |

These small differences do not establish a general speedup. CPU work remains small; browser/Streamlit mounting and scheduling dominate. The harness's polling reports V2 cold opens of 260–367 ms and warm opens of 236–254 ms in the observed run. Browser timestamps avoid attributing that polling interval to application work. The sample size is not a statistical production performance guarantee.

The proven optimizations are structural: one pagination fragment/read per action, and elimination of a settlement round-trip for Checkout reads between 50 and 150 ms. With an 80 ms injected read, the three-sample harness cold median fell from 877 to 367 ms; the loader was still awaited, not hidden. Component updates measured approximately 0.2–0.3 ms in the controlled table test, with the same 34 px geometry.

Checkbox feedback medians were 56–61 ms. Final page-change checks were 224–236 ms, so the 200 ms target is not universal. Returning between full flow workspaces measured 542–1089 ms including a deliberate 200 ms settling allowance; this is distinct from reopening a recipient panel.

The previous multi-second Post Purchase opening figure included waiting for the fixture to create customers, orders, events and flow configuration. The current corrected benchmark separates that 2–3.1 second fixture initialization from the approximately 269 ms panel opening. This is a measurement correction, not a claimed application speedup. The uncorrected operational test still reports 4.3/2.7 seconds desktop/mobile including fixture setup, and 243/253 ms warm reopening. SQL reads were bounded and one per requested page; no Shopify enrichment was introduced.

With 250 ms delayed reads, final cold opens were 852–1379 ms; warm opens were 234–368 ms. The slow-read settlement path remains visible. Neither all cold loads nor every warm sample meets 300 ms.

## Validation and review

- **160 Python tests passed** in the final combined run: shared state/read behavior, lifecycle audiences, order eligibility, consent/suppression, immutable publication, Checkout purchase exits, guarded enrollment requests, sequence/editor save/error boundaries, cache/loading and isolation.
- Five-flow desktop/mobile browser matrix: ten 65-second open sessions, search, pagination, cross-page deselection, collapse/reopen, scroll retention, no unexpected closure or iframe remount, no document overflow.
- Final slow-read matrix: all five sources, 250 ms reads and 35-second refresh windows; selection, scroll and iframe identity retained.
- All five flows passed retained search/status/sort/date controls and failed-read/explicit-Retry recovery.
- Actual shared workspace navigation: open and explicitly closed states plus filters retained for every flow; an edited subject survived direct navigation away and back. An early test incorrectly targeted an outgoing editor before route settlement; the corrected test waits for the requested flow and passed.
- Actual composer: subject edit, draft save, reload and mobile layout passed for all five flows. Full workspace mobile screenshot also checked.
- New interaction suite: all five flows passed detail close/Escape, selection feedback, desktop/mobile layouts, and exactly one fragment/read per page change. Controlled component checks additionally cover focus after reorder, countdowns, recorded status progression, sticky columns, DOM retention and cleanup.
- Real SQL Orders panel: search/date/status/sort, customer diagnostics, selection, background update, desktop/mobile and administrator confirmation **cancel** passed. The shorter operational dwell was supplemented by the shared long-duration matrix.
- Deterministic timer controller tests passed serialization, acknowledgment, dialog resume, detached-controller disposal and bounded terminal settlement.
- Source-scoped Studio verification passed syntax, secret-pattern checks, Studio infrastructure tests and whitespace checks. Render topology validation passed. Self-review found no changes to business rules or publication/delivery paths.

All browser routes were loopback-only and external requests blocked. Data were fabricated; providers and thumbnail prewarming were mocked where applicable. No live personalized preview, thumbnail generation, production network benchmark, full Sports Cave OS bootstrap or multi-hour heap soak is claimed.

## Files changed in V2

Application:

- `crm_flow_recipients.py`
- `crm_automation_analytics_ui.py`
- `crm_lifecycle_ui.py`
- `crm_flow_page.py`
- `components/crm_checkout_table/index.html`
- `components/crm_sections/automation_refresh.js`

Tests and fixtures:

- `tests/test_crm_unified_recipients.py`
- `tests/test_crm_orders_table_ui.cjs`
- `tests/test_crm_automation_refresh_controller.cjs`
- `tests/fixtures/crm_unified_flow_ui.py`
- `tests/fixtures/crm_post_purchase_ui.py`
- `tests/fixtures/crm_lifecycle_preview.py`
- `tests/crm_ui_profile.py` (new)
- `tests/benchmark_crm_email_v2.cjs` (new)
- `tests/test_crm_email_v2_ui.cjs` (new)
- `tests/test_crm_email_v2_navigation_ui.cjs` (new)

Evidence: this report and `docs/email-automation-v2-evidence.json`. The existing untracked V1 evidence JSON and V1 benchmark file were preserved.

## Reproduction

Use the existing local Streamlit/Playwright environment and disposable `tests/crm_postgres_server.mjs`, binding loopback. Fixtures: unified recipients on 18752, SQL Orders on 18738, full workspace on 18751. `V2_PORT=18752` selects the final recipient server for `tests/benchmark_crm_email_v2.cjs`; `V2_REPORT` selects the ignored output filename. `profile=1` enables fixture-only fragment instrumentation. `V2_ONLY` and `V2_READ_DELAY` select a source and injected latency. Browser suites use the same repository runtime helper as V1.

For a V1 comparison, export `crm_flow_recipients.py`, `crm_automation_analytics_ui.py`, `crm_lifecycle_ui.py`, `crm_flow_page.py` and `components/crm_checkout_table/index.html` from the exact baseline commit above into `.tmp-email-v2/v1/`, preserving paths. Start the same fixtures with `EMAIL_V2_BASELINE=1` on ports 18753/18754, then set `V2_PORT=18753`, `V2_SQL_PORT=18754`. The fixture fails rather than silently using current source if the baseline is missing. No checkout/reset/commit is needed.

## Release readiness and remaining blockers

**Ready for email-scope code review; not cleared for coordinated production release.** All five flows retain V1 shared ownership and the focused repairs are locally validated. No migration or service topology change is required.

Branch-wide Studio Verify against its older approved base still fails on the pre-existing potential-secret finding in `tests/test_os_accounts.py:852`, trailing whitespace in `docs/DEVELOPER_STUDIO_V9_LOCAL.md:5–7`, and the extra EOF blank line in `tests/test_files_native_v2_windows.py:78`. The possible secret value was withheld and not dismissed as harmless. These files and the audit rules were not changed. Their owner/security review and the combined release checks remain required.

The worktree is deliberately uncommitted. Production latency, full-shell integration and a longer soak remain release-review limitations. No automatic deployment or production readiness approval is implied.
