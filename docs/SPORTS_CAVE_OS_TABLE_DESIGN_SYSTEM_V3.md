# Sports Cave OS table design system V3

> Release reconciliation: see [final release repair](TABLE_DESIGN_V3_RELEASE_REPAIR.md). The inventory below is historical; the current-main contract covers 148 calls, including the newer Meta temporary table and excluding the removed Flow Settings editor.

## Audit recorded before implementation

Local working-copy baseline: 10 October 2026 (Australia/Sydney). Existing uncommitted changes were preserved. Audit scans tracked application Python/HTML/JS, excludes tests, scripts, temporary checkouts and Shopify theme review copies. Layout grids and outbound email layout tables are not application data tables.

### Native table inventory

Each entry is a rendering call site; a shared renderer may appear in multiple page panels. Function names identify dialogs, expanders and detail views as well as main pages. Line numbers refer to the pre-change working copy.

| File | Line | Renderer / panel | Engine | Prior row height |
|---|---:|---|---|---|
| `ads_creative_refresh.py` | 2536 | `_render_diagnosis` | dataframe | default |
| `ads_intelligence_page.py` | 363 | `_compact_table` | dataframe | default |
| `ads_intelligence_page.py` | 1222 | `render_page` | dataframe | default |
| `ads_intelligence_page.py` | 1283 | `render_page` | dataframe | default |
| `ads_intelligence_page.py` | 1377 | `render_page` | dataframe | default |
| `ads_intelligence_page.py` | 1443 | `render_page` | dataframe | default |
| `ads_intelligence_page.py` | 1265 | `render_page` | dataframe | default |
| `ads_intelligence_page.py` | 1239 | `render_page` | dataframe | default |
| `ads_intelligence_page.py` | 1256 | `render_page` | dataframe | default |
| `ads_meta_review_page.py` | 106 | `metrics_card` | dataframe | 30 |
| `ads_meta_review_page.py` | 413 | `render_campaign_details` | dataframe | 30 |
| `ads_meta_review_page.py` | 432 | `render_creative_selection` | dataframe | 48 |
| `ads_meta_review_page.py` | 553 | `render_campaign_list` | dataframe | 32 |
| `ads_meta_review_page.py` | 505 | `render_page` | dataframe | default |
| `ads_meta_review_page.py` | 561 | `render_campaign_list` | dataframe | default |
| `ads_meta_review_page.py` | 116 | `metrics_card` | dataframe | default |
| `ads_meta_review_page.py` | 211 | `ad_card` | dataframe | default |
| `ads_posting_page.py` | 1431 | `_render_object_result` | dataframe | default |
| `ads_posting_page.py` | 1669 | `_render_recent_posts` | dataframe | default |
| `ads_posting_page.py` | 1638 | `_render_collection_template_copy` | dataframe | default |
| `analytics_page.py` | 271 | `_table` | dataframe | default |
| `app.py` | 11943 | `render_accounts_access_page` | dataframe | default |
| `app.py` | 12793 | `render_active_upcoming_events` | dataframe | 34 |
| `app.py` | 12942 | `render_home_recent_activity` | dataframe | 32 |
| `app.py` | 12889 | `render_home_weekly_work` | dataframe | 34 |
| `app.py` | 13582 | `_render_dashboard_task_csv_preview` | dataframe | 32 |
| `app.py` | 14129 | `render_task_group` | dataframe | 34 |
| `app.py` | 10622 | `_render_developer_allocation_tools` | dataframe | default |
| `app.py` | 10767 | `_render_developer_allocation_tools` | dataframe | default |
| `app.py` | 10853 | `_render_developer_allocation_tools` | dataframe | default |
| `app.py` | 10856 | `_render_developer_allocation_tools` | dataframe | default |
| `app.py` | 10859 | `_render_developer_allocation_tools` | dataframe | default |
| `app.py` | 10862 | `_render_developer_allocation_tools` | dataframe | default |
| `app.py` | 10954 | `_render_developer_allocation_tools` | dataframe | default |
| `app.py` | 10957 | `_render_developer_allocation_tools` | dataframe | default |
| `app.py` | 10960 | `_render_developer_allocation_tools` | dataframe | default |
| `app.py` | 12867 | `render_home_weekly_work` | dataframe | 34 |
| `app.py` | 10771 | `_render_developer_allocation_tools` | dataframe | default |
| `app.py` | 10775 | `_render_developer_allocation_tools` | dataframe | default |
| `app.py` | 10850 | `_render_developer_allocation_tools` | dataframe | default |
| `app.py` | 12213 | `render_settings_page` | dataframe | default |
| `app.py` | 12219 | `render_settings_page` | dataframe | default |
| `app.py` | 12232 | `render_settings_page` | dataframe | default |
| `app.py` | 12249 | `render_settings_page` | dataframe | default |
| `app.py` | 12271 | `render_settings_page` | dataframe | default |
| `app.py` | 12288 | `render_settings_page` | dataframe | default |
| `app.py` | 12345 | `render_settings_page` | dataframe | default |
| `app.py` | 12479 | `render_settings_page` | dataframe | default |
| `crm_automation_analytics_ui.py` | 88 | `checkout_details` | table | default |
| `crm_automation_analytics_ui.py` | 174 | `_checkout_panel` | dataframe | default |
| `crm_automation_analytics_ui.py` | 89 | `checkout_details` | dataframe | default |
| `crm_campaign_analytics_ui.py` | 63 | `email_orders` | dataframe | default |
| `crm_campaign_analytics_ui.py` | 23 | `analytics` | dataframe | default |
| `crm_campaign_analytics_ui.py` | 32 | `analytics` | dataframe | default |
| `crm_campaign_analytics_ui.py` | 103 | `email_orders` | dataframe | default |
| `crm_campaign_home.py` | 190 | `actions` | dataframe | default |
| `crm_campaign_page.py` | 641 | `review_editor` | dataframe | default |
| `crm_campaign_page.py` | 642 | `review_editor` | dataframe | default |
| `crm_campaign_page.py` | 518 | `message_editor` | dataframe | default |
| `crm_flow_builder.py` | 78 | `timing` | data_editor | default |
| `crm_flow_builder.py` | 99 | `test_flow` | dataframe | default |
| `crm_flow_builder.py` | 114 | `activity` | dataframe | default |
| `crm_flow_builder.py` | 121 | `activity` | dataframe | default |
| `crm_flow_page.py` | 162 | `step_performance` | dataframe | default |
| `crm_page.py` | 35 | `table` | dataframe | default |
| `crm_page.py` | 311 | `reports_page` | dataframe | default |
| `crm_page.py` | 312 | `reports_page` | dataframe | default |
| `crm_page.py` | 58 | `profile` | dataframe | default |
| `crm_page.py` | 162 | `segments_page` | dataframe | default |
| `crm_page.py` | 289 | `campaigns_page` | dataframe | default |
| `crm_page.py` | 66 | `profile` | dataframe | default |
| `crm_page.py` | 84 | `profile` | dataframe | default |
| `crm_page.py` | 317 | `reports_page` | dataframe | default |
| `crm_page.py` | 74 | `profile` | dataframe | default |
| `crm_settings_page.py` | 194 | `connections_page` | dataframe | default |
| `crm_settings_page.py` | 146 | `prompts_page` | dataframe | default |
| `crm_settings_page.py` | 232 | `campaign_report` | dataframe | default |
| `crm_settings_page.py` | 236 | `campaign_report` | dataframe | default |
| `crm_settings_page.py` | 221 | `connections_page` | dataframe | default |
| `crm_settings_page.py` | 238 | `campaign_report` | dataframe | default |
| `crm_settings_page.py` | 239 | `campaign_report` | dataframe | default |
| `crm_settings_page.py` | 32 | `campaign_settings_panel` | table | default |
| `crm_settings_page.py` | 269 | `campaign_report` | dataframe | default |
| `design_schedule.py` | 207 | `_render_import_preview` | dataframe | 32 |
| `design_schedule.py` | 861 | `render_design_schedule` | dataframe | 34 |
| `design_schedule.py` | 591 | `dialog` | dataframe | default |
| `design_tracking_page.py` | 186 | `_render_table` | data_editor | default |
| `edition_ops.py` | 2448 | `_render_table` | data_editor | 32 |
| `edition_order_recovery.py` | 157 | `render` | dataframe | default |
| `edition_version_ui.py` | 161 | `release_controls` | dataframe | default |
| `edition_version_ui.py` | 206 | `archive` | dataframe | default |
| `edition_version_ui.py` | 217 | `archive` | dataframe | default |
| `edition_version_ui.py` | 217 | `archive` | dataframe | default |
| `marketing_factory_page.py` | 1534 | `_render_saved_packs_tab` | dataframe | default |
| `marketing_factory_page.py` | 1001 | `_render_meta_signal_panel` | dataframe | default |
| `marketing_factory_page.py` | 1370 | `_render_meta_intelligence_tab` | dataframe | default |
| `marketing_factory_page.py` | 1373 | `_render_meta_intelligence_tab` | dataframe | default |
| `marketing_factory_page.py` | 1405 | `_render_meta_intelligence_tab` | dataframe | default |
| `marketing_factory_page.py` | 1421 | `_render_meta_intelligence_tab` | dataframe | default |
| `orders_page.py` | 2693 | `_render_orders_table` | dataframe | 28 |
| `orders_page.py` | 2673 | `_render_admin_panel` | dataframe | default |
| `orders_page.py` | 2681 | `_render_admin_panel` | dataframe | default |
| `os_pages.py` | 9399 | `render_webhook_events_page` | dataframe | default |
| `os_pages.py` | 9414 | `render_sync_runs_page` | dataframe | default |
| `os_pages.py` | 9429 | `render_app_errors_page` | dataframe | default |
| `os_pages.py` | 9451 | `render_persistence_check_page` | dataframe | default |
| `os_pages.py` | 11360 | `render_developer_widget_status` | dataframe | default |
| `os_pages.py` | 4162 | `_render_prodigi_dispatch_result` | dataframe | default |
| `os_pages.py` | 5486 | `render_supabase_limited_edition_csv_import` | dataframe | default |
| `os_pages.py` | 5507 | `render_supabase_limited_edition_csv_import` | dataframe | default |
| `os_pages.py` | 5510 | `render_supabase_limited_edition_csv_import` | dataframe | default |
| `os_pages.py` | 9213 | `render_product_assets_page` | dataframe | default |
| `os_pages.py` | 1968 | `render_shopify_remote_details` | dataframe | default |
| `os_pages.py` | 8904 | `render_psd_csv_import` | dataframe | default |
| `os_pages.py` | 9001 | `render_psd_csv_import` | dataframe | default |
| `os_pages.py` | 9509 | `render_edition_integrity_check_page` | dataframe | default |
| `os_pages.py` | 11595 | `render_settings_page` | dataframe | default |
| `reporting_page.py` | 375 | `_render_twelve_week_progress` | dataframe | 28 |
| `reporting_page.py` | 564 | `_render_staff_week_activity` | dataframe | 28 |
| `reporting_page.py` | 752 | `_render_sent_reports` | dataframe | default |
| `reporting_page.py` | 801 | `_render_delivery_health` | dataframe | default |
| `reporting_page.py` | 172 | `_render_staff_summary` | dataframe | 28 |
| `reporting_page.py` | 285 | `_render_daily_execution_history` | dataframe | 28 |
| `reporting_page.py` | 432 | `_render_twelve_week_progress` | dataframe | 28 |
| `reporting_page.py` | 513 | `_render_twelve_week_progress` | dataframe | 28 |
| `reporting_page.py` | 591 | `_render_staff_week_activity` | dataframe | 28 |
| `reporting_page.py` | 648 | `_render_operational_activity` | dataframe | 28 |
| `reporting_page.py` | 827 | `_render_delivery_health` | dataframe | default |
| `reporting_page.py` | 1033 | `render_weekly_review_page` | dataframe | 28 |
| `reporting_page.py` | 1054 | `render_weekly_review_page` | dataframe | 28 |
| `reporting_page.py` | 453 | `_render_twelve_week_progress` | dataframe | 28 |
| `reporting_page.py` | 994 | `render_weekly_review_page` | dataframe | 28 |
| `reporting_page.py` | 481 | `_render_twelve_week_progress` | dataframe | 28 |
| `reporting_page.py` | 537 | `_render_twelve_week_progress` | dataframe | 28 |
| `reviews_page.py` | 155 | `importer` | dataframe | default |
| `reviews_page.py` | 168 | `importer` | dataframe | default |
| `seo_page.py` | 219 | `_table` | dataframe | default |
| `seo_page.py` | 2762 | `_render_gsc_import` | dataframe | default |
| `social_media_page.py` | 234 | `_render_team_today` | dataframe | default |
| `social_media_page.py` | 769 | `_render_weekly_summary` | dataframe | default |
| `social_media_page.py` | 806 | `_render_weekly` | data_editor | default |
| `social_media_page.py` | 961 | `_render_history` | dataframe | default |
| `social_media_page.py` | 1012 | `_render_history` | dataframe | default |
| `social_media_workspace.py` | 1666 | `render_plan` | dataframe | default |
| `wall_preview_analytics_ui.py` | 67 | `details` | dataframe | default |
| `wall_preview_analytics_ui.py` | 68 | `details` | dataframe | default |
| `wall_preview_analytics_ui.py` | 69 | `details` | dataframe | default |

### Custom data interfaces

| File / component | Data interface | Assessment |
|---|---|---|
| `app.py` | Activity log HTML table | Apply shared HTML skin; retain columns and title tooltips |
| `os_pages.py` | Fulfilment variant reference HTML table | Apply shared HTML skin; retain all six columns |
| `components/crm_checkout_table/index.html` | Abandoned Checkout email progress | Master reference; retain frozen identifiers, paging, timer and event code |
| `components/daily_planner/index.html` | History; Week Plan objectives; staff weekly summary; daily sheets | Shared HTML skin; retain existing scroll containers |
| `components/daily_planner/index.html` | Editable task rows and tactic rows | Scoped density/borders; multiline inputs and timer controls require taller rows |
| `components/files_window/index.html` | File Details view and list view | Scoped grid skin; retain sorting, selection and navigation |
| `components/files_chunk_uploader/index.html` | Upload queue | Scoped grid skin; retain progress and actions |

### Assessed exclusions

- Outbound email/template presentation tables: `crm_abandoned_checkout`, `crm_campaign_content`, `crm_campaign_footer`, `crm_campaign_html`, `crm_campaign_sections`, `crm_catalogue`, `crm_checkout_elements`, `crm_discount_section`, `crm_email_blocks`, `crm_html_workspace`, `daily_activity_reporting`, `support_email_signatures`, `wall_preview_email`, and HTML under `templates/`. These are email / storefront layouts, not application data grids; changing them would change delivered content.
- `run_migrations.py`: SQL regular expression containing `<table`, not a UI.
- Home planner cards, support inbox message lists, campaign cards, image gallery/thumbnail grids, flow editor nodes, mockup/design canvas, navigation and upload drop zones are not tables. No restyle of these surfaces.
- No AG Grid, external DataGrid library or additional dataframe alias was found in application sources.
- Native renderers cover Orders/Fulfilment, Edition Ops, Social Media, product upload/admin, Design Schedule/Tracking, Creative Refresh, Ads intelligence/Meta Review/Posting, Analytics, SEO, Reviews, Email customers/campaigns/automations/settings, reporting, account/admin, and wall-preview analytics. Modules without actual tables inherit no unrelated layout changes.

## Implementation result

All 147 originally inventoried native call sites were assessed. They receive the shared dataframe theme or static-table CSS. Native grids that previously used default density now explicitly use the shared 34 px token. Existing explicit 28/30/32 px compact rows and 48 px image rows remain deliberate exceptions. All custom data-interface families listed above received the shared scoped skin. No email/template presentation table, chart, card gallery, message list, workflow canvas or unrelated control was intentionally restyled.

Current main includes a temporary Meta campaign table; it inherits the shared theme and retains 32 px rows. Flow Settings is already removed on main and is not restored. The refreshed release contract audits all 148 existing calls, including nine Meta and one CRM flow-history call.

### Shared rules and architecture

- `table_design.py`: 34 px native density token; shared HTML styles; one injection from the existing application style function. No widget wrappers or monkey patches.
- `.streamlit/config.toml`: only dataframe border and header colors change. Borders `#eeece5`; header `#f3f2ec`. Other application theme settings are untouched.
- HTML table paper `#fffefa`, header `#f3f2ec`, separators `#eeece5`, outer border `#e4e2da`, hover `#f7f5ef`, selection `#eee7d7`, focus `#9a7937`. Headers 12 px / weight 600; body 13 px; inherited Sports Cave fonts. Standard cells 34 px with 6 × 10 px padding. No vertical cell borders in shared HTML tables.
- Existing numeric column types retain native right alignment and currency/percentage formatting. Existing date formatting, status meanings, truncation tooltips and column configuration are unchanged. Optional `.sc-table-number`, action and semantic status classes are available to new HTML tables; no status is inferred or reclassified.
- Existing contained scroll regions, frozen identifiers and header positioning remain. Short HTML tables use natural height. Planner tables no longer impose a blanket 900 px minimum on short reports.
- Planner task rows keep multiline inputs, timer controls and natural height. File details/list rows keep their existing engine and selection; upload cells lose vertical boxes. Galleries and unrelated controls are excluded by explicit host/table scopes.
- `scripts/sync_table_design.py` embeds the same CSS into four isolated component frames. Run it after changing the source stylesheet, and run `--check` in validation. There are no runtime CSS fetches, new packages, extra observers, polling, API calls or per-row Python styling work. Each frame adds one style node.
- Future native tables automatically inherit the theme; import `TABLE_ROW_HEIGHT` for density. The regression guard scans all root application Python modules for omitted density. New HTML tables can opt into `.sc-table`; isolated components must embed the shared skin and use an explicit host scope.

### Compatibility exceptions

1. Streamlit 1.58 canvas grids hard-code vertical borders and expose a single color for horizontal and vertical lines. The supported theme makes both faint; removing just vertical lines would require replacing or patching the engine. Canvas typography, header height, built-in sort indicators, focus, hover and selected-cell colors remain native. Native cell backgrounds remain neutral white.
2. Orders/reporting 28 px rows, Meta single-row summaries at 30 px, existing operational 32 px rows, and Meta image rows at 48 px are preserved. Existing fixed maximum viewport heights and image sizes are also preserved. These are intentional functional/density exceptions rather than silently resized click targets.
3. Existing Pandas status styles in Meta Review are retained. Their definitions, thresholds and formatting are unchanged.
4. Existing narrow-view column choices in custom components are retained; no data columns or exports are removed by this task. Canvas grids retain internal horizontal scrolling and virtualization.
5. This is a local visual implementation, not a claim that every production workflow was exercised. Authenticated live APIs, real customer saves, email sending, certificates, allocations and external publishing were not invoked.

## Functional preservation and regression results

All original native calls retain their data expressions, column configuration/order, keys, callbacks, selection modes, disabled columns and return-value handling. The contract suite compares the original 147 call signatures after removing only `row_height`; it permits independently added tables but cannot lose or alter an original call. All four custom component JavaScript bodies are byte-for-byte identical after newline normalization. Skin synchronization and Python syntax checks passed. Render topology validation passed; `render.yaml` was not changed and no Blueprint sync was performed.

| Verification | Result |
|---|---|
| Focused working-copy suite (Orders, Edition Ops editing, Meta tables, reporting, analytics, social, design tracking, reviews, CRM, shared contracts) | 122 run; 96 passed; 26 SQL-dependent skips |
| File manager/upload/product upload/reporting/social reporting/flow builder/analytics navigation group | 140 passed |
| Creative Refresh suite, isolated process | 61 passed |
| Posting handoff suite, isolated process | 15 passed |
| Task-only patch on clean local HEAD snapshot, excluding unrelated work | 83 passed |
| Shared contracts / component skin synchronization | Passed |
| Broad exploratory run | One existing SEO navigation source assertion failed; identical failure reproduced against the captured baseline |
| Planner source contracts | Two existing source assertions failed (top-bar countdown scheduling and authoritative-sheet helper); both reproduced against the captured baseline |

Some combined AppTest runs exposed shared test-state contamination in Creative Refresh/Posting; both complete suites passed in isolated processes. Initial test invocations also named two nonexistent modules; those invocation errors are not application regressions. Windows sandbox temporary-folder/process restrictions initially blocked tests; final runs used a repository scratch directory and local test processes outside the sandbox. No failing assertion was removed or weakened. The three pre-existing source-contract failures remain unresolved because they are outside table presentation.

### Browser verification

Chrome 155.0.8059.39 and Edge 154.0.4258.62 passed the final synthetic browser suite at 1440 px and 390 px widths, with all external browser requests blocked. Checked 50, 250, 500 and 1,000 records.

- Native grid rendering, repeated sorting clicks, filtering, scrolling, correct filtered-record selection (`KEY-0001`), and opening its popup.
- Native keyboard focus/navigation, Enter to edit, Tab to commit a numeric edit, and the local save callback. Editing is an independent fresh fixture session after popup verification.
- Actual Orders renderer with synthetic rows: selection, existing certificate-preview action mocked to a local notice, search by order ID, and narrow layout.
- Actual checkout component: 50 visible rows for every input size, original paging, selection/detail event identity, 34 px rows and contained narrow scrolling.
- Actual Python-generated activity and fulfilment tables; static Streamlit table header colors.
- Planner, file details and upload queue: before/after CSS fixtures using the actual component styles. These are layout fixtures, not full backend-connected component workflow tests. Their scripts are unchanged and existing module tests supplement the layout checks.

Full authenticated navigation through every module, every export/download, and every production save workflow were not browser-tested. The per-module native signature audit covers all identified call sites; browser tests exercise the shared engines plus representative real renderers. Do not interpret synthetic module-selector labels as actual page navigation coverage.

## Performance comparison

Raw measurements: [browser results](table-v3-evidence/browser-results.json). All values below are milliseconds, measured locally. Native Python measurements time the actual `st.dataframe` serialization call in the fixture. Checkout updates use 40 post-warmup samples; pagination limits displayed rows to 50 even for 1,000 source records.

| Records | Chrome native before / after | Edge native before / after | Chrome checkout before / after | Edge checkout before / after |
|---:|---:|---:|---:|---:|
| 50 | 2.63 / 2.30 | 2.85 / 2.39 | 0.10 / 0.20 | 0.10 / 0.20 |
| 250 | 2.95 / 2.11 | 3.86 / 3.03 | 0.20 / 0.10 | 0.20 / 0.10 |
| 500 | 3.02 / 2.67 | 2.75 / 3.68 | 0.10 / 0.10 | 0.20 / 0.20 |
| 1000 | 4.42 / 4.22 | 5.87 / 5.59 | 0.10 / 0.20 | 0.10 / 0.10 |

Native sorting input-to-two-animation-frame timings were approximately 33 ms before and after. Checkout DOM counts increased by exactly one style element (520 → 521 at 50 records; 524 → 525 with pagination). The visible row count and existing node-retaining update engine are unchanged.

End-to-end timings include Playwright actionability waits, Streamlit reruns and machine scheduling. They are noisy and **do not establish a production speed improvement or a blanket no-regression guarantee**. In the final sample Chrome initial load was 2.60 → 2.56 seconds; Edge was 2.09 → 2.61 seconds. Chrome selection was 0.83 → 0.85 seconds; Edge 1.36 → 1.86 seconds. Chrome edit/save was 1.40 → 0.88 seconds; Edge 0.92 → 1.38 seconds. Popup timings were 1.88 → 0.87 seconds in Chrome and 2.40 → 2.39 seconds in Edge. Opposing changes between browsers and earlier runs prevent attributing these differences to styling. No extra data requests or reconstruction logic was introduced, and the measured rendering/sorting paths remain small.

Actual warm navigation between all authenticated pages, production database/network latency, and real save latency remain unmeasured. The existing responsive engines are preserved, but comprehensive production performance acceptance remains a limitation of this local-only task.

## Visual evidence

All screenshots contain synthetic records. Native screenshots are a shared-engine fixture, not live customer pages. Browser assertions cover contained scrolling and selection as well as the images.

| Surface | Before | After |
|---|---|---|
| Native grids, desktop | [Before](table-v3-evidence/chrome-before-native-1440.png) | [After](table-v3-evidence/chrome-after-native-1440.png) |
| Native grids, narrow | [Before](table-v3-evidence/chrome-before-native-390.png) | [After](table-v3-evidence/chrome-after-native-390.png) |
| Checkout, desktop | [Before](table-v3-evidence/chrome-before-checkout-1440.png) | [After](table-v3-evidence/chrome-after-checkout-1440.png) |
| Activity | [Before](table-v3-evidence/chrome-before-activity.png) | [After](table-v3-evidence/chrome-after-activity.png) |
| Fulfilment reference | [Before](table-v3-evidence/chrome-before-fulfilment.png) | [After](table-v3-evidence/chrome-after-fulfilment.png) |
| Planner table CSS fixture | [Before](table-v3-evidence/chrome-before-daily_planner-1440.png) | [After](table-v3-evidence/chrome-after-daily_planner-1440.png) |
| File details CSS fixture | [Before](table-v3-evidence/chrome-before-files_window-1440.png) | [After](table-v3-evidence/chrome-after-files_window-1440.png) |
| Upload queue CSS fixture | [Before](table-v3-evidence/chrome-before-files_chunk_uploader-1440.png) | [After](table-v3-evidence/chrome-after-files_chunk_uploader-1440.png) |

Additional Edge equivalents, 390 px custom-host captures, and actual Orders renderer captures are in `docs/table-v3-evidence/`. The final CSS-only pass corrected the fixture's planner header markup; it made no application change. See `css-results.json`.

## Files changed by this task

- `.streamlit/config.toml`
- `ads_creative_refresh.py`
- `ads_intelligence_page.py`
- `ads_meta_review_page.py`
- `ads_posting_page.py`
- `analytics_page.py`
- `app.py`
- `components/crm_checkout_table/index.html`
- `components/daily_planner/index.html`
- `components/files_chunk_uploader/index.html`
- `components/files_window/index.html`
- `crm_automation_analytics_ui.py`
- `crm_campaign_analytics_ui.py`
- `crm_campaign_home.py`
- `crm_campaign_page.py`
- `crm_flow_builder.py`
- `crm_flow_page.py`
- `crm_page.py`
- `crm_settings_page.py`
- `design_schedule.py`
- `design_tracking_page.py`
- `edition_order_recovery.py`
- `edition_version_ui.py`
- `marketing_factory_page.py`
- `orders_page.py`
- `os_pages.py`
- `reporting_page.py`
- `reviews_page.py`
- `scripts/deploy_table_design_v3.ps1`
- `scripts/sync_table_design.py`
- `scripts/test_table_design_v3.py`
- `seo_page.py`
- `social_media_page.py`
- `social_media_workspace.py`
- `table_design.py`
- `tests/fixtures/table_v3_contracts.json`
- `tests/fixtures/table_v3_preview.py`
- `tests/test_table_design_v3.py`
- `tests/test_table_design_v3_ui.cjs`
- `wall_preview_analytics_ui.py`

Also this report and `docs/table-v3-evidence/*`. The local handoff bundle `docs/table-v3-release/{changes.patch,manifest.json}` contains only verified task changes and hashes; it is not added to the deployment commit. `tmp/table-v3-*` snapshots, diagnostics and release-validation copies are local-only and excluded. Existing unrelated edits in shared files are excluded from the patch.

## Reproduce locally

Run `python scripts/sync_table_design.py --check` and `python -m unittest tests.test_table_design_v3`. The broader module suites listed above use the repository's existing tests. Run UI suites separately when using AppTest to avoid shared state contamination.

Run `python scripts/test_table_design_v3.py` with Node Playwright available on `NODE_PATH` and Chrome/Edge installed. The runner uses disposable loopback ports, synthetic fixtures and owned process cleanup. If the local `tmp/table-v3-baseline` snapshot exists it captures before/after; otherwise it validates the current version only. Screenshot output is under `docs/table-v3-evidence`. No live credentials are required.

## Manual deployment handoff

No commit, push, merge, deployment, production database mutation, Shopify change, Meta campaign change or customer-data modification was performed.

The single command below runs the included manual release script. It verifies the frozen patch and asset hashes, creates a separate temporary clone of the configured origin, fetches main, checks/applies only this task's patch, stages its exact allowlist, validates topology/styles and runs focused regression suites before committing. Your original repository index, uncommitted changes and untracked files are not stashed, reset or staged. Conflicts/test failures stop before push. A remote race causes the ordinary fast-forward push to fail; no force push is used. The temporary clone remains available for inspection. Successful push to main triggers the existing Render auto-deployment; no Blueprint sync or service creation is performed.

The regenerated package is pinned to GitHub main `aa40acf66c7dcf7db7159fb1485f5bdc3265bbeb`. Its exact frozen index, file hashes and current regression gates are validated by `-VerifyOnly` in a fresh remote clone before the manifest can be marked verified. Any change to GitHub main stops publication. See the release repair report for baseline failures and the manifest verification receipt.

```powershell
& { $ErrorActionPreference = 'Stop'; Set-Location -LiteralPath 'C:\Users\hello\Documents\sports-cave-image-factory'; & '.\scripts\deploy_table_design_v3.ps1' }
```
