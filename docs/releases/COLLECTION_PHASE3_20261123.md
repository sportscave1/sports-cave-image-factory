# My Collection performance phase 3 — local only

Task `20261123-1ab85cd4`, owner `codex-collection-phase3-20261123`.
Production base `daec97e570fb6abcbff7a9245c798a64ff6f92e9`. This isolated working copy contains the completed local Phase 1/2 changes and the latest local certificate master/subtitle adjustments, copied without modifying their original task worktrees. No commit, push, deployment or production mutation is authorized or performed.

## Result

“Pairs with your edition” briefly reuses the expensive candidate assembly and smart ranking work. It continues to show the same two eligible cards, in the same smart order, with the same layout and product links. There is no change to recommendation weights, sport memberships, title inference, prices, variants, checkout, order submission or multi-item processing.

The new private candidate cache stores only product IDs and their collection grouping, never full product records, prices, credentials or customer profiles. The key hashes the shop namespace, source display-cache identity/generation, authenticated owner, complete current owned-product set, selected seed edition, country and ranking recipe.

Each request still authenticates through the existing API, reads current purchase/certificate ownership, validates that the seed is owned, and resolves catalogue eligibility. A changed purchase set selects a different cache key. Missing ownership or a failed history read never serves a warm result. Product/edition eligibility is rechecked on warm requests, and the native account still performs its Storefront availability/publication check before selecting the two cards. There is no new price/stock cache.

The native component now checks cancellation immediately after the recommendation response. If the customer has changed editions, an obsolete response does not start another Storefront query. A query already started cannot be cancelled by this guard; its result remains protected by the existing cancellation check before updating the UI.

## Bounds and invalidation

- Candidate entries expire after 120 seconds, with up to 128 entries / 2 MiB retained encoded bytes per worker. Transient decoding, hashes and Python object overhead are additional.
- Up to eight unique candidate loads can be pending. Identical concurrent requests share a result. Saturation returns a temporary-unavailable response for the recommendation section; it does not alter certificate loading or cart behavior. Failed loads are not retained and can be retried.
- The existing `DisplayCache` gains a monotonic generation counter. Every actual cache invalidation increments it, while repeated invalidation with the same version remains a no-op. All existing get/put/clear behavior is preserved. Candidate keys include this generation, so a result finishing after invalidation cannot become a hit for a new generation.
- Expired results are not served as stale fallbacks. There is no persistent cache, new service, disk, database migration or storage write. Worker restarts are cold.
- Ranked signals may lag by up to the candidate TTL. Underlying memberships/tags retain the pre-existing Shopify display-cache TTL; this layer does not make those sources fresher. The existing optional analytics fallback remains in use if the ranking snapshot cannot be read. Current purchase ownership is never supplied by this cache.

## Synthetic evidence

The integration check makes two consecutive calls for the same owned edition and country:

| Work | First request | Warm request |
| --- | ---: | ---: |
| Purchase-history lookup | 1 | 1 |
| Certificate ownership lookup | 1 | 1 |
| Collection-membership assembly | 1 | 0 |
| Collection-products assembly | 1 | 0 |
| Tag-query batches for the small fixture | 1 | 0 |
| Ranking-snapshot lookup | 1 | 0 |
| Catalogue eligibility resolution | 1 | 1 |

The fixture's nearest subject match remains first. Tests also change ownership and sold-out status between calls and verify exclusion, preserve legacy collection balancing, check country/owner/shop separation and TTL/byte limits, share in-flight work, reject unauthenticated warm requests and retry failed loads. A native component test verifies obsolete responses skip the next query and current responses still retain smart order while removing unavailable products.

The underlying Shopify adapter already caches many provider reads. The table demonstrates skipped assembly/lookup work, not a claim that every cold lookup previously made a network round trip. No live page-load, SEO score or real-user latency improvement has been measured. These are authenticated account UX improvements; public storefront indexing is unchanged.

## Verification

- The combined Phase 1/2/3, CRM provider/cache, certificate, print-download, framing and order-certificate suite passed 116 tests plus 3 subtests. The subsequently added legacy-balancing case passed with all 13 Phase 3 checks, giving 117 distinct passing checks across these runs.
- 41 Node checks pass, including native cancellation, two-card ordering, purchased variants, multiple-item image mapping, photo/video routing and cart preservation.
- Project TypeScript, Shopify app configuration, local Shopify production build, Render topology and whitespace checks pass. The account bundle remains approximately 18.2 KB compressed.
- The standalone Shopify Toolkit component validator still cannot start because its installation lacks `typescript`; the project's TypeScript/compiler and Shopify build pass.
- A broader CRM logic check encounters the existing Svix verification test failure: the local Python installation has no `svix` package. `crm_resend.py` and that test were not changed. Earlier unrelated source-assertion/account-query failures are documented in the Phase 2 report; they were not rewritten here.
- Development uses synthetic records and disposable PGlite. Local browser preview remains disabled, and no real customer review, email, purchase or supplier action was performed.

Evidence: `C:/Dev/SportsCaveWorktrees/.studio/runtime/20261123-1ab85cd4/` (`focused-python.log` and validation receipts). All task worktrees remain available for review, with no commits made. Generated build outputs remain local.

Phase 4 timing instrumentation and live validation remain separate work. A future authorized release must publish the backend to the existing canonical Sports Cave OS service before publishing the account extension. This document is not release authorization.
