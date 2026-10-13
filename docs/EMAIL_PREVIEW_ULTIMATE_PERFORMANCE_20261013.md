# Email preview performance — local verification

2026-10-13 · Task 20261011-54d8ff88 · Local implementation only.

## Actual root causes and changes

- Lifecycle rendering hydrated the whole document for production sizing, again for the visual editor, and again for each isolated section. The production renderer now shares its resolved document with the visual compiler: one hydration on the normal path, with only changed sections compiled.
- Header/footer shells were compiled again after middle-section edits. Lifecycle shells now have a bounded session cache. Production sizing and the local visual output retain separate caches; the Abandoned Checkout cache remains unchanged.
- Large verified order histories were repeatedly JSON-hashed. Each immutable selected preview snapshot now receives a session fingerprint, renewed after verification/refresh. Authoritative test verification still compares the actual customer/order facts and detects changed artwork.
- Different HTML edits could start concurrent jobs for identical image facts. Jobs now share dependencies and memoise visual order/product/catalogue reads within the same customer revision. Real delivery and fresh test rendering bypass these visual reads.
- Cached native recommendation facts were not recognised by the ready check. They now render immediately without scheduling another background compilation.
- PostgreSQL EXPLAIN ANALYZE found a repeated paid-order anti-join scan in Welcome. A null-safe hashed paid-customer lookup preserves eligibility and avoids the nested scans. Other candidate queries were not changed.
- Initial pending content now mounts the existing email shell and iframe boot source. It updates in place, preserves unsaved editor sections, and never borrows the previous recipient’s image. Background failures retain only the same customer/order/document’s valid preview, with actionable diagnostics. Stale completion/error results cannot override the active selection.
- Full-document validation errors no longer remove valid neighbouring editor sections. Validation remains visible; production and test delivery safeguards remain enforced. Contradictory cached customer/order associations are rejected.

## Measurement scope

Actual Streamlit and Chrome were exercised with the real shared toolbar, preview renderer and client section composer. Shopify responses used realistic synthetic customer/order/product DTOs with 40 ms latency per API call; SQL responses in the browser fixture were synthetic. These are **not production integration timings**. Separate actual PGlite PostgreSQL plans use 1,000 synthetic subscribers, 800 orders, 11,600 webhook events, existing indexes and an unowned null-customer order. No production credentials, customer data or external provider requests were used.

Cold measurements use five new browser sessions per flow. Warm operations use 20 samples; cached switches use 11 samples after the first selection. Values below are milliseconds, shown as median / empirical p95. Navigation setup waits outside the timed interval for the preceding native widget acknowledgement to settle. Customer-switch timing ends at the correct name/artwork, before closing the picker. The save fixture measures the UI version acknowledgement, not production database save latency; actual persistence is tested separately.

## Cold first frame and personalised completion

First frame means the existing email shell can be visible while verified artwork is still loading. Personalised completion means the correct selected example’s content is present. A cached preview is not proof of fresh delivery permission.

| Flow | First frame before | First frame after | Personalised before | Personalised after |
|---|---:|---:|---:|---:|
| Abandoned Checkout | 398 / 435 | 428 / 505 | 413 / 451 | 444 / 519 |
| Welcome | 512 / 520 | 400 / 425 | 526 / 534 | 477 / 524 |
| Post Purchase | 587 / 638 | 413 / 426 | 609 / 651 | 631 / 640 |
| Win Back | 668 / 692 | 408 / 428 | 681 / 705 | 632 / 646 |
| Fulfilment | 601 / 682 | 417 / 429 | 614 / 695 | 640 / 649 |

The lifecycle shell appears sooner. Fully personalised cold completion did not improve uniformly: Post Purchase and Fulfilment were slightly slower in this five-session sample. Required fresh verification and Streamlit startup remain material costs; no cold production latency claim is made.

## Warm operations after optimisation

| Flow | Reopen | Cached customer switch | Server HTML update | Desktop/mobile | Save acknowledgement | Client HTML processing |
|---|---:|---:|---:|---:|---:|---:|
| Abandoned Checkout | 103 / 119 | Not changed / not benchmarked | 116 / 120 | 67 / 83 | 55 / 66 | 0.4 / 0.6 |
| Welcome | 100 / 119 | 139 / 154 | 112 / 116 | 51 / 67 | 49 / 65 | 0.1 / 0.3 |
| Post Purchase | 101 / 115 | 176 / 193 | 112 / 119 | 66 / 67 | 49 / 65 | 0.5 / 0.7 |
| Win Back | 105 / 116 | 161 / 179 | 112 / 118 | 50 / 67 | 49 / 51 | 0.4 / 0.6 |
| Fulfilment | 102 / 105 | 160 / 176 | 114 / 116 | 63 / 67 | 49 / 52 | 0.4 / 0.5 |

Warm median and p95 targets passed in this controlled run. The immediate client editor was already fast and remains fast. Native server-driven text fields include framework/network acknowledgement time. Abandoned Checkout customer switching was deliberately not reimplemented or exercised through a new adapter; its existing regression suite and visual-path benchmarks remain the control.

## Warm before/after comparison

| Flow | Reopen median before → after | Server HTML median before → after | HTML p95 before → after |
|---|---:|---:|---:|
| Abandoned Checkout | 105 → 103 | 121 → 116 | 133 → 120 |
| Welcome | 104 → 100 | 107 → 112 | 209 → 116 |
| Post Purchase | 107 → 101 | 115 → 112 | 224 → 119 |
| Win Back | 101 → 105 | 114 → 112 | 121 → 118 |
| Fulfilment | 102 → 102 | 112 → 114 | 119 → 116 |

## Requests, compilation and bottleneck contribution

| Flow | Hydration calls before → after | HTML compilations before → after | Shopify calls before → after | SQL calls before → after |
|---|---:|---:|---:|---:|
| Abandoned Checkout | 164 → 164 | 42 → 42 | 0 → 0 | 0 → 0 |
| Welcome | 166 → 108 | 56 → 23 | 4 → 4 | 1 → 1 |
| Post Purchase | 168 → 111 | 57 → 23 | 10 → 10 | 6 → 6 |
| Win Back | 168 → 111 | 57 → 23 | 10 → 10 | 6 → 6 |
| Fulfilment | 169 → 111 | 57 → 23 | 10 → 10 | 6 → 6 |

Counts cover the complete identical browser protocol, including two verified lifecycle examples and measurement acknowledgements. Basic purchased galleries already avoided repeated warm network calls; their necessary cold/switch calls were retained. Pure editing/device changes add no Shopify requests. The reduction is in hydration, shell compilation and redundant work on richer template transitions.

A separate same-customer Products Purchased → Collections transition reduced added Shopify calls from **4 to 2** (the exact order and purchased products were reused). It took **857 → 250 ms** in the synthetic-network browser check, rendered six appropriate recommendation images, and made no extra customer verification call.

The one-page synthetic Welcome verification cost approximately 81 ms (customer + history). Paid-order flows cost approximately 122 ms (customer + history + operational facts); initial verified artwork resolution was approximately 81 ms (exact order + product lookup). Those are sequential required reads in this fixture, not live Shopify measurements. The reported first-frame timing separates them from the presentation shell. Warm direct browser section processing was below 1 ms median. Per-flow cumulative hydration and compilation times, exact request counts and uncached-switch timings are retained in the JSON evidence.

Actual PostgreSQL warm query medians/p95: Welcome **28.9/30.8 → 1.8/2.3 ms**. The unchanged Post Purchase, Win Back and Fulfilment queries remained approximately 9–10 ms median on the dataset. The before Welcome plan repeatedly scanned/materialised paid customers while seeking the first 50 subscribers without purchases; the after plan uses a hashed subplan. These are local PostgreSQL execution measurements, not Supabase connection/network timings.

## Functional and safety verification

- Final fresh-database run: 251 Python tests passed with zero failures or skips, including real disposable PostgreSQL publication, immutable versions, rollback/retry, consent/suppression, cancellation/refund, pause/resume, unsubscribe, exact variant/quantity gallery handling and authorised test-rendering safeguards.
- Native Chrome/Streamlit acceptance passed all five flows, correct customer switching, retained refresh, six matching collection products, HTML edits/reopen, and desktop/mobile. The toolbar stayed exactly 40 px at widths 1100, 600, 390 and 320.
- The steady browser protocol attached 21 frames per flow after optimisation: the initial iframe plus 20 deliberate close/reopens. Editing, viewport changes, save acknowledgements and recipient changes did not create extra preview iframes. Lifecycle before counts were 22; Abandoned Checkout remained 21.
- New regression tests cover one hydration across sections, incremental compilation, deduplicated in-flight image jobs, session/recipient isolation, large-snapshot fingerprints, stale jobs, retained failures, contradictory cached order ownership, and fresh test artwork comparison.
- Existing production publication/trigger/delivery code and Abandoned Checkout loading, resolver, test destination and safeguards were preserved. No original template, saved HTML, schedule, customer record or sending history was edited.
- An intermediate repeat on a reused disposable database correctly rejected a synthetic checkout token retained from an earlier run. Repeating on a fresh database passed without changing Abandoned Checkout or its idempotency safeguards.
- Diff whitespace and canonical Render topology checks passed. Final Studio verification/results are recorded as local Tested; no commit or deployment.

## Limitations and readiness

Ready for local code review. Production performance and actual Shopify API/network latency remain unverified under repository local-only rules. Actual cold history pagination, provider configuration, product image download/decode time and network/database connection overhead can differ from the fixtures. The first meaningful frame is a loading shell when appropriate facts are unavailable; it does not claim verified customer content. Production/test delivery still performs authoritative verification, and a stale failed artwork preview must be refreshed before a matching test can be sent.

The local publication regression suite logs optional thumbnail prewarm `browser_runtime_unavailable`; it does not affect the tested email HTML or preview canvas. No real test email, production email, flow activation, commit or deployment was performed.

## Files changed

Runtime: `crm_flow_preview.py`, `crm_local_preview.py`, `crm_automation_preview_cache.py`, `crm_abandoned_checkout_ui.py`, `components/crm_sections/preview.js`.

Verification: `tests/test_crm_lifecycle_preview_performance.py`, `tests/test_crm_ultimate_preview.py`, `tests/fixtures/crm_ultimate_preview.py`, `tests/benchmark_crm_ultimate_preview.cjs`, `tests/benchmark_crm_preview_cold.cjs`, `tests/benchmark_crm_gallery_reuse.cjs`, `tests/profile_crm_preview_queries.mjs` and this report.

Evidence: `.tmp-preview-ultimate/before-browser.json`, `after-browser.json`, `cold-browser.json`, `gallery-reuse.json`, `query-plans.json`, `final-tests.log`, `browser-regression.log`. Before source snapshots remain in `.tmp-preview-ultimate/before-*.py`.
