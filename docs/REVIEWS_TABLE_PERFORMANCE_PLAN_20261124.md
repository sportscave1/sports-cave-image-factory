# Reviews table repair, speed test and phase plan

24 November 2026. The user authorised the OS table repair, speed testing, phased plan and Git/Render release. This change concerns the private OS Overview only; review content, public storefront widgets, account forms and automations are unaffected.

## Phase 1 — compact, responsive presentation

Implemented in this release:

- Use the list container's actual width, including space taken by the sidebar. At wide sizes, align a six-column table with a dedicated 168px action area. Below 1050px of list space, show compact review cards rather than compressing every field into narrow columns.
- Product name has a real text element, normal word wrapping, two-line clamp and full title tooltip. Open displays the full product title and review. Review snippets are bounded; source/date and publication status remain readable. Rating-only records retain their four stars and stay published.
- Open and Edit are native, explicitly labelled 80px buttons. Labels remain visible at narrow widths; phone actions have 44px minimum height. Remove the nested Streamlit columns that previously squeezed them.
- Reuse the existing 136px WebP thumbnail transformation, with explicit 42px layout dimensions, lazy loading and async image decoding. No original-size product image is needed for normal Shopify product thumbnails.

## Phase 2 — reliability and measured performance

Implemented and tested:

- Correct Next/Previous to request a full rerun; the old fragment-scoped rerun was invalid outside a fragment. Pagination remains 25 displayed rows plus one sentinel record.
- Preserve existing bounded background read pool, per-session cache and last-good data. No added resize observers, polling timers, database queries or provider calls.
- Real browser test against a synthetic loopback-only Streamlit fixture at 1920, 1440, 1366, 1024, 881, 750, 430, 390, 375 and 320px widths, including sidebar effects. Assert no horizontal overflow, two-line product text, readable full button labels and bounded row height. Check Open, Edit/save, pagination, resize cache reuse, one-second delayed storage failure and subsequent recovery.
- Nineteen focused Python tests passed; 28 database-dependent cases were intentionally skipped in this presentation-only regression run. The real browser scenario passed across all ten widths and interaction/failure checks. Compilation, diff and canonical Render topology checks passed.

### Measurements

Synthetic localhost fixture, headless Edge, 25 rendered reviews from 52 fabricated records; third-party transports blocked and tiny substitute thumbnails used. These are rendering/interaction measurements, not production network or real image-transfer benchmarks.

| Measurement | Before | After |
|---|---:|---:|
| Fresh-session rows, three samples at 881px | 2075 / 1987 / 2078ms | 1669 / 2008 / 2093ms |
| Median of those samples | 2075ms | 2008ms |
| Long review content block at 881px, excluding native actions | 774px high | 137px high |
| Main-content DOM elements | 1893 | 1535, about 19% fewer |

Separate final ten-width run: first 25 rows in 1723–2076ms, median 2037.5ms; next page 554ms; last-good rows confirmed still present 82ms after starting a delayed failure. All ten sizes had no horizontal overflow; no JavaScript page exceptions. Resizing reused one table read and one summary read rather than requesting new data. Final row containers measured 67–225px high across the tested sizes.

Production read-only SQL measurement: the actual first-page ordering uses `sc_reviews_received_page`, returns 26 rows, hits 12 shared buffers with zero reads, and executes in 0.401ms (planning 1.383ms). The database is not the observed first-load bottleneck. Before deployment, two authenticated live reload-to-first-row checks measured 5145/5179ms, including browser-control and network overhead. Do not equate the ~2s localhost fixture with the live app's total startup time.

Evidence: local `artifacts/reviews-table-responsive-20261124/` contains `benchmark.json`, `before-after.json`, before/after screenshots and the exact baseline module from the prior commit. Only synthetic records were used in development; no live credentials, customer submissions, emails or rewards were involved.

## Phase 3 — live release acceptance

Release through the existing Git main / Render services, keeping the canonical primary identity. Verify the precise release commit is Live, then test the actual signed-in OS at a wide desktop size, the reported 881px width and a phone size. Confirm product clamping, visible Open/Edit labels, no horizontal overflow, Open/Edit dialogs and next/previous navigation. Close editors without saving during layout acceptance. Check that E Maddock's prior correction remains rating-only and that published totals remain 209. Record live timing and proof screenshots with the release evidence and Studio status.

Rollback if necessary is a focused reversal of this presentation/pagination change on the current branch; preserve the existing editor, audit data, unread notifications and unrelated account-extension release. No database migration, service replacement or theme publication is involved.

## Phase 4 — next measured optimisation cycle

1. Establish at least 20 authenticated navigation samples split by first load, warm navigation and page changes. Use the existing `reviews stage=... duration_ms=...` logs to separate connection/authentication, background-pool queue, SQL and client rendering. Initial budgets: local 25-row display <=2.5s median, warm page changes <=1s, and no additional reads on resize. Treat these as test budgets, not universal guarantees.
2. If live startup remains above 3s consistently while SQL remains below 50ms, focus a separate change on shared OS startup/authentication and read-completion delivery. The present live baseline is about 5.2s; do not add indexes, services or faster polling to a healthy SQL query without evidence.
3. Add the synthetic responsive/interaction test to an isolated browser CI job before changing Streamlit versions. Keep all provider transport blocked; run with a fresh local server after imported code changes. Gate on 320–1920px, sidebar open/collapsed, Open/Edit accessibility, pagination, no-op/audit behaviour and delayed/failing storage recovery.
4. Revisit indexing, archival or page transport only if real review volume changes measured query/transfer cost. Retain 25-row pagination, server-only audits and the existing small WebP thumbnails. No ongoing scheduled job or customer-facing automation is needed for this plan.
