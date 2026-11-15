# Orders compact layout verification

## Changes

- Removed the automatic-payment-sync description and both dynamic fulfilment-row captions.
- Kept the Orders heading; scoped 22px type, compact margins and top padding.
- Kept the existing submitted search form, Enter submission, Search button and Latest 50 behavior; removed its border and visible input label.
- Moved search controls onto one desktop row. Certificate/fulfilment actions use Streamlit's supported wrapping horizontal container, with selection count at the end and manual certificate controls still conditional.
- Removed the unused leading action column and outer table card padding. Existing table columns, selection key, 28px rows, copy/Prodigi/file handlers and status styling remain intact.
- The actual dataframe resize container follows viewport height; browser assertions check that the canvas is resized, not clipped. No additional viewport listeners or polling.
- Selection now normalizes selected rows only; the display projection reuses rows already normalized by table rendering. No new cache or backend calls, no changes to async loading, source refresh, sorting, canonicalization, permission checks or operational writes.

## Files

- `orders_page.py`
- `orders_page.css` (Orders-only style fragment)
- `tests/test_orders_loading_ui.py` (removed-caption expectation; toolbar test doubles support existing button methods)
- `tests/test_shopify_sync.py` (removed-caption expectations)
- `tests/test_orders_compact.py`
- `tests/fixtures/orders_compact.py`
- `tests/test_orders_compact_ui.cjs`
- `scripts/benchmark_orders_compact.py`
- This report.

## Measured layout

Windows Chrome, actual Orders rendering and application CSS with a synthetic fixed 64px top bar and fabricated 62 fulfilment units from 50 orders. This fixture does not reproduce the entire authenticated production shell/sidebar. Coordinates are CSS pixels from the viewport top.

| Viewport | Heading before → after | Table before → after | Table higher | Final grid height |
| --- | --- | --- | --- | --- |
| 1920 × 1080 | 144 → 80 | 585.6 → 212 | 373.6 | 760 |
| 1440 × 900 | 144 → 80 | 585.6 → 212 | 373.6 | 656 |
| 1280 × 720 | 144 → 80 | 600.4 → 212 | 388.4 | 476 |
| 390 × 844 | 144 → 78 | 738.8 → 352.4 | 386.4 | 404 |

The heading gap below the fixture navigation is now 16px on desktop and 14px on mobile. At 1440 × 900 the recovered vertical space exposes approximately 13 additional 28px rows immediately.

Screenshots and machine-readable measurements are in:
`C:/Users/hello/.codex/visualizations/2026/10/07/01a11866-64ce-7c01-b425-63f51af54c1b/orders/`
(`before-1920.png`, `after-1920.png`, and corresponding 1440/1280/390 files; `before.json`, `after.json`).

## Performance

`scripts/benchmark_orders_compact.py` compares HEAD row preparation with the updated path, verifies identical display output, then takes the median of seven runs of 100 iterations over 62 synthetic units with no selection:

- Before: **2.943ms**, 186 normalizations in selection/table/projection.
- After: **1.114ms**, 62 normalizations in the same portion of the path.
- About **62% less CPU time in that measured portion**, saving 1.829ms per render. Other canonicalization still runs unchanged.

Browser readiness timings vary with asynchronous fixture loading (roughly 1.5–4 seconds across runs). No end-to-end navigation speed improvement is claimed from these samples. No production latency or database performance claim is made.

## Tests

- Broad existing Orders loading, recovery, selection and fulfilment suites plus new compact tests: **148 passed / 155**, seven legacy failures.
- Focused Shopify Orders/allocation-unit tests: **3 passed**.
- Certificate action state and manual certificate controls: **22 passed**.
- The seven broad-suite failures concern unchanged Edition Ops, mockup and product-upload source expectations. All seven also failed when tested against HEAD modules in memory. They were not removed or weakened.
- Browser checks at all four sizes: captions absent, no horizontal page overflow, no heading/input overlap, matching canvas/grid heights, Enter search yields one expected unit, Search restores all 62 units, no Streamlit exceptions. Desktop selection and mocked Preview Certificate action passed.
- Modified Python compilation and `git diff --check` passed. This targeted Python/CSS change has no separate frontend bundle build.

## Limits and rollout

Windows WebView2 was not available for direct testing. Real certificate generation/uploads, Shopify operations and production database access were deliberately excluded; existing isolated tests cover those action paths. The screenshot reference in this request was not attached, so measurements use the actual repository layout fixture.

No schema migration, configuration change or new dependency. Include the Orders style file alongside `orders_page.py` in the normal deployment. No push or deployment performed. No production records changed.
