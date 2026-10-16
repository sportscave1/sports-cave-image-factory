# Orders badge and performance repair — 16 October 2026

Based on production b177b3ea26e3a3f14bb4b48eaabe6b5f80ff770b.

## Original actionable-order rule

Count distinct orders with at least one eligible paid/partially paid/partially refunded line still needing internal certificate or dispatch work, across all dates. Internal terminal dispatch wins; missing later certificates never reopen completed orders. Explicit nonterminal dispatch overrides Shopify's order-level fulfilment fallback. Pending/full refunds and cancellations suspend or close processing. Removed refunded lines do not create work.

## Production audit and cause

The badge displayed 53 during inspection (the user had seen 55). All 53 were June orders whose financial status had been refreshed by refund reconciliation while local fulfilment was NULL. The refund query already fetched Shopify fulfilment but discarded it. Read-only Shopify inspection confirmed all 53 FULFILLED. Their 65 local lines were counted as 53 distinct orders, so line duplication was not the cause.

The 21 paid/unfulfilled Shopify orders were separately checked against internal dispatch: 20 were Complete, including multi-product orders, and SC3303 was Refund Pending with no current items. Shopify's nine partial refunds were fulfilled or cancelled. The independent actionable-order count at audit was 0. Reconciliation, rather than a hardcoded subtraction or manual order edits, repairs local evidence.

## Changes

- Keep latest Shopify fulfilment, cancellation and complete current-line quantities in the existing Orders refund projection; preserve internal completion priority and edition history.
- Recover missing historical fulfilment snapshots in a bounded pass alongside normal rotating reconciliation and pending-refund checks.
- Materialize compact incomplete-dispatch candidates before reading large order JSON. Normalize numeric/GID aliases once and preserve terminal-first/latest dispatch selection.
- Keep the one-query aggregate and existing coalesced 30-second server cache/60-second browser cadence. No full Orders snapshot fallback on database failure. Expire unverified browser badge values after two minutes; no extra polling loop.
- Timestamp-only reconciliation no longer invalidates Orders or changes its visibility timestamp. Status/financial/quantity changes still invalidate it.
- Materialize optional metadata once per selected order in the bounded latest-50/search base query, preserving schema compatibility and every returned field.
- Reuse JPG/PSD resources for selected details and the table; overlap independent stored resource reads using the existing bounded executor. No Shopify/Dropbox refund lookup in row rendering.
- No HTML, CSS, columns, layout, table keys, selection, search or scroll mechanism changed in Orders. Only existing sidebar count freshness handling changed in the top-bar JavaScript.

## Measured database performance

Read-only EXPLAIN ANALYZE against the current 560-order production database, ten repeated samples per final variant. Empirical p95 uses nearest rank; these are SQL execution times, not browser page times.

| Badge aggregate | Median | p95 | Queries | Shopify calls |
|---|---:|---:|---:|---:|
| Before | 50.01 ms | 74.75 ms | 1 | 0 |
| After, before backfill | 18.19 ms | 21.24 ms | 1 | 0 |

The latest-50 base query was profiled separately on the same 126 production rows: ten paired SQL samples improved from 68.95 ms median (79.02 ms p95) to 13.97 ms median (17.91 ms p95). Both queries returned the identical full-result digest c165968a723dcb44218a7f45abad7540 before reconciliation; no selected data was dropped. One production end-to-end base snapshot sample was 3.101 seconds, including 1.059 seconds in the base phase and about 1.1 seconds of connection setup. Connection and transport latency remain a larger cost than SQL execution and must not be presented as eliminated.

A production reconciliation check caught PostgreSQL operator precedence in the first deployed semantic JSON comparison; that transaction rolled back. Parenthesizing the JSON extraction corrects it. The corrected expression was validated directly against PostgreSQL before the follow-up release, and final reconciliation must succeed before completion is claimed.

A separate earlier single observation was 282.607 ms before; do not compare that single observation with repeated warm samples or claim a cold-browser p95.

Browser observation baseline: reload 11.360 and 12.261 seconds; warm navigation back to searched Orders 4.625 seconds; search 8.380 seconds including automation observation overhead. Too few browser samples for defensible p95. Production after-deployment observations are recorded separately with release evidence.

The existing Orders reader remains bounded to latest 50 and five batched SQL phases. Certificate generation, Shopify writes and edition operations are not part of sidebar calculation. Stable resource reads remain fresh; the resource reuse is per render, not a stale cross-session cache.

## Validation

Focused regression set: 99 passing tests covering badge policy, aliases, multiple products, partial/pending/full refunds, cancellations, coalescing/expiry, non-semantic events, resource concurrency/reuse, bounded latest-50 retrieval, database recovery, async loading and webhook health. A read-only PostgreSQL VALUES fixture independently returned exactly orders A and F (2), excluding completed aliases, pending/full refunds, zero-current lines, cancellations and fulfilled historical snapshots.

The broader legacy EditionOpsUiTests class contains unrelated obsolete source-contract expectations against newer Edition Ops, prompt and JPG interfaces; it is outside this repair and was not changed to fit this release.

Production edition/certificate baseline digests: edition_orders 55d2b4aebfb7c57e61d3e0a0bc840343; certificates e47a100a4f5a7f52ee7fb957b4911fd3. No allocation, numbering, certificate history or Shopify metafield write path was added or changed.
