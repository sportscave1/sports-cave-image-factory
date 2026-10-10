# Automations Flow V4 — UI, speed and thumbnails

Local release audited against `02c81f1d4dcb2c572e63d8aa4004766d458b634d`. No commit, push, deployment, live lifecycle action, production database write, Shopify change or email send was performed.

## Verified Email 3 failure

Read-only SQL confirmed Abandoned Checkout — Wall Preview 1 is ACTIVE with publication v10 and all three immutable templates present. The third stage maps to template `a7e71b9c-2a9d-5657-949a-64f720dd05a2`, version 10. Its exact saved document contains discount tokens and an existing saved Shopify offer; its original durable thumbnail key is in ERROR. No recipient or checkout customer tables were read.

The original renderer processed checkout placeholders before substituting the saved discount. `crm_abandoned_checkout.hydrate()` therefore raised `ValueError: Unresolved checkout template syntax`. Running the exact published source through the original renderer reproduced `email_render_failed`. The revised renderer resolves the saved offer first, then lowers checkout content and neutral personalisation. The isolated latest-main implementation produced a decoded, valid 240×316 WebP (6054 bytes). Source and image hashes are recorded in [verification evidence](flow-v4-evidence/published-source-verification.json). The actual source and image remain local temporary evidence and are excluded from the public release package.

This verifies the affected source locally. The production image remains ERROR until this release is manually deployed and an authorised page requests regeneration. No publication, immutable template or existing cached production row was altered.

## Interface and operational access

Recipient timelines and Abandoned checkouts are no longer rendered below the main email sequence. Admins reach the existing operational controls through Diagnostics → Open operational diagnostics, with a Back to Flow action. Existing permission checks, recipient inspection, checkout search/filtering, manual enrolment and scheduling backend functions are retained. Non-admins cannot enter this route. Flow Settings remains removed. No analytics/customer requests are made merely to render the removed panels.

The shared page uses Segoe UI, restrained gold actions, consistent 32px controls, status pills, aligned tabular metric numbers and subtle row separators. Subject/preheader remain intact; summaries wrap to two bounded lines and source text remains accessible through titles and Edit Email. Changed draft text is explicitly labelled when the thumbnail shows the immutable published source. All eight summary calculations and reporting periods are unchanged; unavailable reads render dashes. Table Design V3 row-height integration from current main is preserved.

![Before, desktop](flow-v4-evidence/chrome-before-1440.png)

![After, desktop](flow-v4-evidence/chrome-after-1440.png)

![After, narrow phone](flow-v4-evidence/msedge-after-320.png)

## Implemented performance changes

1. Immediate private-cache display before any thumbnail wake, without a source/DB read on a private cache hit.
2. Maximum two rendering subprocesses instead of a single serial worker; bounded 24-job queue, cross-process disk claims and fenced durable leases prevent duplicate generation. CRM_THUMBNAIL_WORKERS may reduce this to one on constrained hosts.
3. Full WebP decode/dimension validation, bounded stat-addressed validation cache, corrupt-asset regeneration and concurrency-fenced invalidation. Renderer revision webp-2 invalidates the old failure/address without modifying the email.
4. Existing session definition cache reused for sequence rendering, with a fresh updated_at check on fragment reruns; the already authenticated route row seeds the initial render. Mutation handlers retain fresh database locks/revision checks.
5. Removed unconditional 300ms browser-wide scanning. Scoped mutation observation and intersection-driven one-shot wake timers stop when no pending visible previews remain. Trusted pointer, keyboard and focus input defers optional wakeups for one second so user actions take priority on the native event channel. Off-screen stages remain lazy; IDs survive reorder and distinguish draft/version/flow.
6. Safe stage failure categories, finite wake/retry budgets and full-preview access. Preview errors do not block other stages or delivery.

## Measurements

All times are milliseconds, shown as p50 / nearest-rank p95. Browser runs use real local Chrome/Edge and mocked immutable documents/analytics; these are fixture results, not production latency guarantees. Warm navigation includes a full browser reload and is deliberately broader than a Python-only timing. Five warm samples per flow size/browser; first load is retained separately as the cold sample. Six samples per menu/preview and real-editor transition. Three cold queue repetitions and 100 cache-hit samples. Small sample p95 is the observed maximum; it is not a reliable population estimate.

| Browser | Stages | Before warm rows | After warm rows |
|---|---:|---:|---:|
| chrome | 1 | 335.57 / 345.96 | 334.96 / 346.70 |
| chrome | 3 | 343.91 / 411.08 | 369.91 / 385.69 |
| chrome | 6 | 423.30 / 450.59 | 427.88 / 467.04 |
| chrome | 12 | 518.13 / 527.67 | 603.15 / 639.71 |
| msedge | 1 | 309.56 / 324.27 | 320.65 / 333.58 |
| msedge | 3 | 429.20 / 464.69 | 336.55 / 340.30 |
| msedge | 6 | 479.96 / 500.34 | 415.44 / 419.31 |
| msedge | 12 | 570.42 / 594.04 | 509.78 / 543.23 |

| Browser | Cold 3-stage rows, before / after | Warm first cached image after rows, before / after |
|---|---:|---:|
| chrome | 451.75 / 409.40 | 41.02 / 47.51 → 15.10 / 35.20 |
| msedge | 338.35 / 337.21 | 46.27 / 103.01 → 14.05 / 18.35 |

| Browser | Menu | Full preview open | Full preview close | Actual editor open | Actual editor return |
|---|---:|---:|---:|---:|---:|
| chrome | 62.56 / 80.66 | 249.49 / 275.84 | 246.27 / 252.41 | 271.37 / 368.27 | 403.19 / 446.02 |
| msedge | 54.51 / 75.26 | 240.38 / 265.19 | 242.44 / 249.18 | 287.17 / 352.76 | 382.01 / 891.54 |

| Thumbnail component | Before | After |
|---|---:|---:|
| Cold queue stage 1, request to ready | 1525.72 / 1662.27 | 1715.36 / 1805.76 |
| Cold queue stage 3, request to ready | 4434.91 / 4441.30 | 3347.93 / 3644.48 |
| Cold queue stage 6, request to ready | 8779.00 / 8869.98 | 5031.24 / 5387.14 |
| cache_before, 100 private hit requests | 0.213 / 0.363 | — |
| cache_after, 100 private hit requests | 0.126 / 0.169 | — |

After pipeline queue wait across 18 jobs: 1701.13 / 3620.94; renderer subprocess duration: 1699.60 / 1833.28. Cache hits never invoke the loader. Inlined private WebP transfer/display timing is included in the browser readiness measurements; no independent production network transfer measurement was made.

Cold thumbnails remain asynchronous and can take seconds. Warm-flow <350ms is met only in some local cases, not universally; Edge/large flows and p95 remain above it. Menu and private cache targets are supported by local measurements; preview/editor targets are not production guarantees. Some regressions/variance remain visible in the raw results and tables. Neither publication validation nor scheduling checks were removed to meet targets.

## Regression and browser results

The exact isolated release gate ran 516 tests: 515 passed, one exact expected failure. The failing frozen-version discount-delivery assertion also fails on unchanged current main (`New future version` vs `Your offer: FIXTURE5`). The gate still executes it and only classifies that exact exception/message/assertion location; any new failure or unexpected success stops release. This sending-policy discrepancy is outside this UI task and remains explicitly unresolved. Final thumbnail tests ran 26 tests and passed, including two additional corrupt-image/concurrent-replacement cases; these overlap the broad run and are not added to its count.

Chrome and Edge passed save timing, duplicate, reorder, add, reload, analytics refresh, admin Diagnostics route and actual editor open/return using disposable PostgreSQL and mocked Shopify/Resend. The 1/3/6/12-stage visual/navigation/thumbnail matrix passed in both browsers, including later-stage scrolling, immutable version labels, full-preview open/close and no page exceptions. Both browsers passed 1920, 1440, 1366, 1024, 750, 430, 390 and 320px overflow checks; 32 before/after screenshots are retained. Summary metric labels and exact fixture values are checked. Original browser duplicate timeout was a test click during post-save fragment replacement; the test now awaits scoped DOM settlement and verifies the persisted result. It does not catch or waive failed actions. A separate intermittent Edge failure during rapid editor transitions exposed competing thumbnail wake events; trusted user input now postpones optional wakeups. Rapid transitions then passed in both browsers without adding a wait to the transition loop.

Cache/SQL tests cover deduplication, restart/durable reuse, corrupt assets, stale leases, old-owner fencing, storage failure, immutable source identity, publication invalidation, reordered/disabled stage IDs, neutral dynamic previews, network allowlisting and untouched delivery/analytics tables. Existing eligibility, consent, unsubscribe, suppression, purchase-exit, cooldown, publication, scheduler and duplicate-send tests remain in the release gate. Pause/resume/publish/send controls were not activated in browser tests; existing mocked unit confirmation/permission coverage is retained. Canonical Render topology validation passed; render.yaml and sending/publication worker code are unchanged.

## Shared future-flow architecture

One renderer owns header, analytics, stages, settings, preview and transitions. Only the admin operations branch is trigger-specific. Cache/source tests exercise abandoned, welcome, post_purchase and win_back with 1/3/6/12 stable stage IDs, disabled stages and reordered rows. Future entry/eligibility rules remain backend responsibilities; no future flow was created, activated or published.

## Remaining limits and release

Production UI and post-deployment regeneration are not verified. Render memory/CPU with two concurrent Chromium instances is not measured; the cap is two and can be configured to one. Privacy allowlisting can omit non-raster or non-approved remote assets (the affected sample logo is unavailable), while retaining the actual email content/layout. No external tracking or customer-context lookup is enabled.

The full 24-operation performance decomposition is not complete: independent Python rerun/DB timing, real production analytics refresh/date-switch response, repeated add/save/reorder p50/p95, rapid cross-flow navigation and editor before/after timing have not all been separately instrumented. The report therefore makes no complete production speed claim. All available raw timings, stage-size coverage and source repair evidence are included.

The manual PowerShell helper validates checksums, clones an isolated checkout, fetches latest main, applies only reviewed hunks after conflict checking, runs the broader gate and both browser suites, verifies an exact staged allowlist, rechecks main and performs an ordinary push. Your original branch, index and uncommitted work remain untouched. Concurrent changes that conflict stop before commit. A non-fast-forward push is never forced. The existing primary Render service and existing automatic deployment are used; no new service or Blueprint sync is requested.

Email Editor V6 files and its release package are excluded. Flow changes apply as hunks to current main so unrelated Table Design, Navigation, Meta Review and Design Studio work is not copied from older snapshots. The sole baseline sending assertion remains a release caveat. Run the supplied single manual command only when ready to release.
