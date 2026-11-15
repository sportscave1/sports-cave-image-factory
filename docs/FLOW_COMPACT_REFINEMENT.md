# Compact Flow refinement — 8 October 2026

## Scope and implementation

This change only refines the existing unified Automation Flow workspace and its directly shared helpers. It does not deploy, publish flows, alter customer email HTML, change the scheduler, or migrate production data.

- Neutral rectangular 32px controls, compact toolbar and eight summary metrics. Gold remains reserved for the actionable publishing button.
- Revenue is replaced by Orders in the Flow summary and email rows. Revenue calculations and stored records remain available to other reporting callers.
- Performance History and Recent Activity are no longer rendered or requested by Flow. The report's daily chart aggregation is omitted for Flow only. Automations Overview activity remains intact.
- Email sequence, lazy thumbnails, shared email editor, publishing/version logic and cached background reads are retained.
- Flow Settings is permanently visible below the sequence. A form batches editing locally; its explicit save persists a draft through the existing save function.
- Operational recipient timelines remain available on demand in a compact popover.
- Abandoned Checkouts loads on demand inside its own fragment. SQL keyset pagination selects at most 51 base records before expensive joins, displays 50, and performs server-side search. Search, filter and selected checkout identities survive closing/reopening. Selections on other pages are retained; Add to flow explicitly applies to selected records on the visible page.

## Cause and isolation

The settings and checkout disclosures had `on_change='rerun'` outside their inner fragments. Opening them reran the enclosing editor/Flow fragment, reconstructing rows and thumbnails and repeating reads. This was a broad Flow rerender, not necessarily a complete top-level Streamlit script rerun. Step saves also explicitly requested an application rerun.

The disclosure now belongs to the checkout fragment; settings have their own form/fragment. Analytics controls and step metrics update independently. Read-only metric placeholders are replaced without reconstructing email rows or thumbnails. Stable step/form keys avoid resetting controls after another section saves. Draft saves update the existing toolbar through its native refresh control, using the same scoped-control mechanism already used by the editor. No polling framework, arbitrary delay or dependency was added.

Actual navigation into the shared email editor still uses the existing application navigation rerun. This is distinct from harmless in-page interactions.

## Orders attribution

Counts use the existing canonical `crm_order_attribution` ledger and its `eligible` flag, automation identity and immutable email step identity. Its Shopify order primary key prevents repeated events from counting the same order twice. Eligibility is maintained by the existing purchase/attribution pipeline; abandoned checkouts and clicks are not counted as orders.

The current system defines conversions using the same eligible attributed orders, so Conversions/Sales and Orders currently match. This change does not invent a different conversion definition. No estimated revenue-to-order conversion is used. If analytics cannot be loaded, the interface displays an unavailable value rather than invented counts.

## Local measurements

Chrome/Playwright, 1440px desktop viewport, disposable PostgreSQL-compatible fixture with mocked provider/Shopify and blocked external network. These are individual local samples, not production benchmarks or guarantees. Interaction timings include browser synchronization and instrumentation. First-load samples below use a fresh browser after fixture initialization; process startup and synthetic fixture seeding are excluded.

| Operation | Before | After |
| --- | ---: | ---: |
| Initial Flow usable | 470ms | 435ms |
| Settings editing | 350ms | 132ms |
| Open checkout section | 2,002ms | 1,281ms |
| Checkout search | 380ms | 327ms |
| Step menu | 222ms | 206ms |
| Date filter response | 434ms | 250ms |
| Open shared email editor | 416ms | 389ms |
| Return to Flow | 246ms | 361ms |

Returning to Flow was slower in this sample and should not be claimed as improved; both samples remain within the requested warm-navigation range. Cached checkout reopening measured 910ms in the final sample, with zero SQL reads; earlier samples varied up to 1.8s. This still has room for improvement in the existing Streamlit/component lifecycle.

Settings editing went from three reads and one Flow reconstruction to zero of either. Opening checkouts went from four reads and one Flow reconstruction to one bounded read and zero Flow reconstructions. Search now performs one bounded server query instead of filtering an already downloaded history in the browser. Date changes still fetch the necessary summary and per-step analytics asynchronously; the sample's immediate counter does not represent all eventual background reads.

For settings, checkout opening/search, step menus and date changes, browser checks confirmed retained thumbnail DOM, zero Flow/application rerenders and zero sampled animation frames missing the thumbnail. Actual editor navigation intentionally replaces the Flow view and is excluded from that assertion.

Raw timing artifacts: `tmp/flow-compact-before.json`, `tmp/flow-compact-after.json`. Screenshots: `tmp/flow-compact-after.png`, `tmp/unified-flow-*.png`.

## Files

- `crm_flow_page.py`: compact styling, fragment isolation, Orders labels, settings, metric placeholders and removed Flow history/activity loading.
- `crm_automation_analytics_ui.py`: optional paginated checkout UI, retained selection and scoped invalidation.
- `crm_checkout_analytics.py`: optional keyset/search query, Orders projection and history-free report option.
- `crm_automation_toolbar.py`: Flow-only lazy Test popover using the existing simulation.
- `crm_flow_builder.py`: optional fragment scope for operational recipient retry UI; default behavior preserved.
- `tests/test_crm_flow_compact.py`: real SQL attribution and pagination checks.
- `tests/fixtures/crm_flow_refinement.py`, `tests/test_crm_flow_refinement_ui.cjs`: baseline/current profiling and DOM stability regression harness.
- `tests/test_crm_flow_page_ui.cjs`: verify reordered identities, explicitly dismiss retained native step menus, and await preview closure before responsive assertions.

## Verification and limitations

Final results: **133 unit/integration tests passed in 32.590s**, both browser suites passed, Python compilation passed, and `git diff --check` passed. Browser tests cover the compact view, absent history/activity, retained Overview activity, independent metric refresh, draft settings persistence, correct publishing indicator, selection/search restoration, pagination, step editing/add/duplicate/reorder/disable/delete, thumbnail invalidation, shared editor navigation, 12-step flows and widths down to 320px.

SQL/integration tests use only a disposable local database and mocked delivery provider. They cover unique order attribution, independent step counts, preserved revenue/history, paging/search, published versions, manual enrollment, consent, suppression, timing, duplicate prevention and worker behavior.

There is no separate frontend production-build, lint or static-type target for these Python/Streamlit modules. Python compilation and the executable SQL/browser suites are used. Production latency, prolonged sessions, CPU/network throttling and live Shopify/provider behavior have not been certified by this local refinement test. No database migration, service configuration or deployment is required by the change itself.

Reproduction: start `tests/crm_postgres_server.mjs` on the disposable fixture's normal port, then run `streamlit run tests/fixtures/crm_flow_refinement.py` on port 8892. With the existing Playwright runtime in `NODE_PATH`, run `node tests/test_crm_flow_refinement_ui.cjs` and `FLOW_URL=http://127.0.0.1:8892/ node tests/test_crm_flow_page_ui.cjs` sequentially. Baseline mode uses `FLOW_PROFILE_BASELINE=1` and reference `01bc526` (override with `FLOW_PROFILE_BASELINE_REF`). Run SQL tests only after browser tests because they reset fixture records.
