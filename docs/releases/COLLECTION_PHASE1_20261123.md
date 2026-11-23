# My Collection performance phase 1

Phase 1 is implemented locally. Publishing requires fresh release authorization.

## Result

- The page requests `bootstrap?include_review=false`. Signed certificate assets and frame pricing can become ready independently of the review provider. Legacy bootstrap callers retain the previous default review payload.
- A separate authenticated GET `/api/collector-vault/review-prompt` loads review eligibility using the session owner. Its database/provider work and bootstrap work execute in the existing thread pool rather than on the asynchronous request loop. Review errors have an independent retry; they do not reload the collection or its offers.
- During a rolling release, the page can still use a review prompt from an older bootstrap server. No customer data is persisted or shared between mounted accounts.
- Recommendation ranking and ownership exclusions are unchanged. The optional `fields=ids` response sends only the eight ranked candidate IDs. Storefront reads title, handle, product-wide market availability and a 400px image instead of up to 100 variants per candidate. The two visible cards retain rank, publication and availability filtering. Prices/options continue to load on the linked product page; certificate frame pricing/cart validation is unchanged.
- Purchased-artwork thumbnails request at most 320px from public Shopify CDN URLs. Review fallback imagery uses 480px and frame swatches use 320px. Existing version parameters and smaller thumbnails are retained; signed URLs, certificate sources and print downloads are not resized.
- Recommendation placeholders reserve approximate card space using the final two-column structure. Existing image aspect ratios remain explicit. These reduce movement; zero layout shift on every screen is not claimed.

## Tradeoffs and boundaries

There is an additional small authenticated review-options request, including a separate ownership read. This isolates the optional provider dependency; it does not remove the provider call. Private preview caching/rendering, recommendation ranking caches and full real-user timing instrumentation remain phases 2–4. The original three-colour preview rendering and supplier/fulfilment processes are untouched. A pre-existing mixed text encoding in account-commerce.js was normalized to UTF-8 while editing that module.

## Validation

- 70 Python tests and 11 subtests pass, including API authentication, session ownership, old/new response compatibility and a controlled slow-review test proving frame bootstrap completes while the review lookup is still blocked.
- 47 Node checks pass, including smart ordering/availability, cart preservation, thumbnail version/signature handling and existing UI checks.
- Native TypeScript check, Shopify config and production build pass. Storefront GraphQL query validates against 2026-04 schema.
- No production speed claim is made from local checks. Live native-account display and review/frame/recommendation loading must be observed after release, without submitting a real review or purchase.

## Release sequence

After approval, publish the backend to the existing canonical Sports Cave OS service, wait for its healthy live deployment, then publish the account extension. No service creation, infrastructure change, database migration or customer-data backfill is required. The previous API shape remains valid for older account versions.
