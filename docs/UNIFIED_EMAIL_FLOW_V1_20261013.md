# Unified Email Flow System V1

Implemented locally on 13 October 2026 in task `20261011-54d8ff88`, owner `me/email-flow-fix`. Abandoned Checkout remains the master interface. No commit, push, deployment, production mutation, customer enrollment, flow activation, schedule change or real email send was performed. All database writes and delivery simulations in tests used disposable loopback fixtures and mocked providers.

## Root causes

The Flow page, toolbar, sequence operations and email composer were already shared; rebuilding them would have introduced another implementation. Recipient behaviour had diverged: lifecycle disclosures lived inside refreshing fragments, Welcome/Win Back invalidated cache generations on refresh and issued extra reruns, Post Purchase alone had callback/context fencing, and Checkout separately merged selection events. Hidden widgets lost their filters. Conditional loading controls shifted the table's Streamlit position during slow reads. Repeated customer detail reads bypassed the bounded background-read path.

Pre-change browser checks reproduced loss of the 210 px internal scroll position in Welcome and Win Back. They did not reproduce every reported production symptom, so this is not a claim that all historical production failures had one cause.

## Shared implementation

- `crm_flow_recipients.py` owns the disclosure shell, retained controls, bounded cached reads, stale/error states, fixed settlement slots, one table declaration and fenced event callback. Refresh observations cannot overwrite newer selection. Explicit header deselection clears selections across pages; individual changes retain other pages.
- `crm_flow_recipient_adapters.py` supplies labels, fields, sort/filter options and recipient projections. Delivery cells reuse the Checkout progress renderer and published step identities rather than matching editable drafts by position.
- `components/crm_checkout_table/index.html` is the only browser table. Checkout styling and 34 px rows apply to every source; the separate order-only styling and event protocol were removed. Modern compact controls share the master stylesheet. Scroll offsets survive remounts through per-flow session storage; no customer data is stored there.
- Existing `crm_flow_page.py`, sequence controls, editor, template library, publication and save boundaries remain shared. No copies of those interfaces were added.
- Slow reads share a bounded 150 ms wait, followed by a one-shot 250 ms settlement wakeup. The fixed loading/error slots preserve table position. Checkout enrollment progress retains its independent receipt polling, without a duplicate table settlement timer.

## Flows and necessary differences

| Flow | Recipient source and retained operations |
|---|---|
| Abandoned Checkout | Existing incomplete-checkout query, keyset pagination, recovery/progress, guarded repair and enrollment requests |
| Welcome Series | Existing subscription/consent audience and subscription timing; subscriber fields |
| Post Purchase | Existing order-first ledger, payment/order checks, explicit administrator enrollment confirmation and fulfillment fallback controls |
| Win Back | Existing inactivity rules, last purchase, paid-order/value fields and timing |
| Fulfilment Follow-up and native/legacy flows | Read-only recorded enrollment history through `crm_native_audience.py`; no inferred eligibility or historical backfill |

All use the common Flow page/editor, recipient shell, read/state layer and Checkout table. Checkout keeps its source-specific action controls and cursor pagination; lifecycle sources keep their existing filters/date criteria. No consent, suppression, unsubscribe, deduplication, recovery, scheduler or provider authority was changed. Lifecycle queries now include per-step receipts only after selecting a bounded page (51 records including the next-page sentinel).

## Performance

Paired five-sample medians in milliseconds, Chromium at 1440 px, 50 visible rows, fresh browser sessions, synthetic 20 ms data reads and already-running local fixture servers. Warm samples reopen the same 50 rows. These measure panel interaction, not production network latency or server process startup.

| Flow | Initial opening before → after (ms) | Warm reopening before → after (ms) |
|---|---:|---:|
| Abandoned Checkout | 239 → 236 | 245 → 246 |
| Welcome Series | 1370 → 236 | 235 → 250 |
| Post Purchase | 241 → 234 | 247 → 249 |
| Win Back | 1368 → 232 | 246 → 240 |
| Fulfilment Follow-up | N/A → 234 | N/A → 248 |

Welcome and Win Back improve by about 83% on initial opening. Checkout, Post Purchase and warm opens remain effectively unchanged; small millisecond differences are normal measurement variation. Fulfilment previously had no recipient table, so a before-table timing is unavailable.

With deliberately slow 250 ms reads, final cold opens were 0.83–1.38 seconds and warm reopens 0.23–0.25 seconds. These include the visible initial read/settlement transition; loading is not hidden. All five maintained selection, 210 px scroll and iframe identity through a 35-second slow-read refresh window. The faster fixture additionally passed 65 seconds open for every flow at both 1440 and 390 px.

The 10,000-customer/10,000-order SQL fixture retained one query per lifecycle page and zero Shopify calls. First-page medians were Welcome 41.41 → 44.23 ms, Post Purchase 68.86 → 43.17 ms and Win Back 53.41 → 54.80 ms. Post Purchase SQL was unchanged, so its difference is measurement variation, not an optimization claim. Welcome/Win Back now include more receipt information with a small bounded cost. The material opening improvement comes from shared loading/settlement and retained state, not a claimed database speedup.

The real synthetic Post Purchase SQL/UI fixture passed at desktop/mobile: initial opening 3292/2695 ms, warm reopening 227/232 ms, two selections 378/418 ms. Its larger first-open overhead remains a local end-to-end limit, not an instantaneous-opening claim. The controlled 50-row browser table measured 0.3 ms median / 0.5 ms p95 update time.

## Validation

- 137-test Python regression suite passed; eight shared-layer tests also passed after final settlement changes. Coverage includes eligibility, consent/suppression, immutable publication, purchase exits, guarded enrollment requests, editor/sequence saves and errors, late-event rejection, bounded stale-state retention, and native read-only history.
- An earlier timing-sensitive worker test failed during a contended fixture run. Its isolated 25-test suite and the subsequent full 137-test run both passed.
- Five-flow desktop/mobile browser matrix: opening, reopening, expand/collapse, search, pagination, global deselection, background refresh, scroll retention and document overflow. All ten 65-second sessions passed without unexpected closure or iframe remount.
- Five-flow slow-read matrix: fixed table identity, selection and scroll through pending/settled refresh; passed for every source.
- Five-flow controls/error suite: retained search/status/sort/date filters, warm scroll, narrow layout, failed initial read and explicit Retry recovery.
- Five-flow actual shared-composer suite: subject edit, draft save/reload and mobile layout. Preview uses synthetic/missing-example states; no live personalized customer preview or delivery was requested.
- Existing Checkout browser regression passed (dynamic columns, acceptance evidence, countdowns, bounded polling, DOM retention, sticky scroll and cleanup). Updated order-table and real SQL Orders-panel regressions passed, including customer diagnostics and enrollment confirmation, which was cancelled.
- Render topology validation and the current working-diff whitespace check passed. Full app bootstrap and production preview remain outside Phase 1 authorization.

Raw timings are in `docs/unified-email-flow-v1-evidence.json`. Reproducible test sources include `tests/test_crm_unified_recipients.py`, the three `test_crm_unified_*_ui.cjs` suites, `tests/benchmark_crm_unified_flow_ui.cjs`, and `tests/fixtures/crm_unified_flow_ui.py`. Browser fixtures bind loopback only and block external requests. Baseline mode uses the pre-change UI modules/table saved beneath ignored `.tmp-unified-flow`; these can be reconstructed from baseline commit `8a593ef4ccf8eac094777adf665b65de0de56c9d`. Optional thumbnail prewarming was mocked in the main Python run; actual thumbnail image generation is not claimed tested here.

## Files changed

Application: `crm_flow_recipients.py`, `crm_flow_recipient_adapters.py`, `crm_native_audience.py`, `crm_flow_page.py`, `crm_automation_analytics_ui.py`, `crm_lifecycle_ui.py`, `crm_lifecycle_audience.py`, `crm_post_purchase_audience.py`, `components/crm_checkout_table/index.html`.

Tests/fixtures: `tests/test_crm_unified_recipients.py`, `tests/test_crm_unified_flow_ui.cjs`, `tests/test_crm_unified_controls_ui.cjs`, `tests/test_crm_unified_editor_ui.cjs`, `tests/benchmark_crm_unified_flow_ui.cjs`, `tests/fixtures/crm_unified_flow_ui.py`, `tests/fixtures/crm_lifecycle_preview.py`, `tests/test_crm_checkout_live_ui.cjs`, `tests/test_crm_checkout_operations_ui.cjs`, `tests/test_crm_flow_refinement_ui.cjs`, `tests/test_crm_orders_panel_ui.cjs`, `tests/test_crm_orders_table_ui.cjs`. Existing browser selectors now point at the single component owner; the order-row expectation now matches Checkout's 34 px geometry.

Evidence: this report and `docs/unified-email-flow-v1-evidence.json`.

## Deployment readiness

The flow changes are implemented and locally tested, uncommitted, and retained in the assigned worktree for coordinated review/integration. No migration, Render configuration or production credential change is required by this change.

Branch-wide Studio verification against its older approved base remains blocked by pre-existing unrelated findings: a possible-secret pattern in `tests/test_os_accounts.py`, Markdown trailing whitespace in `docs/DEVELOPER_STUDIO_V9_LOCAL.md`, and an extra EOF blank line in `tests/test_files_native_v2_windows.py`. Values are withheld; those files were not edited. The branch is not marked release-ready. Release coordination must resolve/review those findings, commit the approved combined changes, run the combined release checks and obtain deployment authorization. Production latency and the complete live OS shell remain unverified.
