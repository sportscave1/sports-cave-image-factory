# Orders speed — Phase 4 final release, 22 November 2026

## Completed

The Orders table now receives account-authorised deltas from the existing local mirror. It checks while visible every five seconds, pauses when hidden, and retries with backoff while retaining the last good screen. The old five-second whole-page refresh loop is disabled once the table owns live updates, including an in-flight legacy marker check. No browser navigation or full-page rerun is needed for arrivals.

Only changed/new row payloads are sent. Unchanged DOM rows stay in place. Keyed insertion/removal preserves the visible row anchor, page, checkbox selection, draft search, open review panel and its scroll position. A fragment-only acknowledgement adopts the server-cached authoritative snapshot so selecting a newly arrived row cannot revert to the older Python view. Account/search generations reject late responses. Exact immutable unit identity can transfer selection when allocation arrives; customer names never do.

The table remains 50 units per page and includes every unit in its bounded latest-75-order result. An opened/selected row that falls outside that result stays visible read-only until searched again. Later-page and open units receive status priority within the existing 200-ID status read budget. Status errors and regrouping use the same stable viewport path. Full-resolution artwork still loads only on click; the row feed downloads no images.

The read-only source reuses the existing cell/link presenter, original variant mappings and batched local JPG/PSD/status reads. It makes no Shopify, Dropbox or Prodigi network calls and performs no allocation, payment, submission or certificate mutation. Bounded per-actor/query/permission caches coalesce duplicate reads; snapshots expire after 30 seconds even if arrival markers are unchanged, covering mapping/certificate updates. Authentication is checked on every request, including unchanged revisions. No credentials or raw customer rows are logged. Safe backend timing metadata measures the feed.

## Previous phases retained

Phase 1: fast admission, sequential variant/upload/item QA, final whole-order QA and one submission fence.
Phase 2: short product/upload/QA and submission-preflight transactions, per-phase source batching and concurrent Reset protection.
Phase 3: Companion 1.7.36 paired readiness notifications, replay cursor, retry keepalive, isolated authentication budget and fallback alarm.

Supplier countdown/preferences, owner-controlled final release behaviour, tax policy, insert presence policy, exact artwork/variant/edition/address checks, uncertain-write safeguards, customer certificate timing and duplicate-order consolidation checks are unchanged. No new extension reload, services, schema or webhook subscriptions are needed for Phase 4.

## Validation

Synthetic real-browser tests exercise the actual component and intercepted local fixture responses: arrivals keep DOM identity, viewport anchor, selection, search and drawer scroll; a fragment acknowledgement keeps them stable; full artwork loads only after click; later pages and failure/recovery retain the review. Unit/API tests cover delta identity, authentication and account isolation, expiry, source failure, concurrent builds, generation changes, newly arrived selection, exact-unit transfer, read-only retained rows, pagination and stale-progress protection. Existing automation and loading tests are rerun for this release.

Production acceptance must use genuine incoming orders. Do not reset already submitted or paid customer orders to manufacture a test, and do not claim live separate-purchase merging acceptance without an eligible same-customer/same-address unpaid pair. Supplier response/rendering times remain outside this page optimisation; no software can guarantee never failing.

Final regression audit: 425 Python checks passed plus 70 Node checks. The broad legacy UI module has 18 failures asserting retired Orders/Edition Ops/product-prompt screens; exporting and testing the released a33b05f0 source reproduced the identical 18 failures (119 legacy checks passed). No new failure was introduced, and unrelated retired-screen assertions were not rewritten to mask them. Full comparison evidence is retained locally in the task verification record. The final modified feed/browser subset was rechecked after the stale-fragment guard.
