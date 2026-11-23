# Completed collection performance and certificate release

The user explicitly authorized finalizing Phase 4 and publishing all completed work on 23 November 2026: “finalise now weith phase 4 finish the entire thig off then push eveyrhitng live up to date finsihed”.

Task `20261123-9c2e1a01`, owner `codex-collection-release-20261123`. This isolated release candidate combines Phases 1–4 and the revised certificate master/subtitle design. Earlier task worktrees are preserved. The release targets the existing `sports-cave-os` service (`srv-d8kl4on7f7vs73dvavv0`) in Nathan's previously confirmed Render workspace and the existing Sports Cave OS Shopify account extension. No infrastructure, scope or pairing changes are included.

## Completed behavior

- Optional review eligibility loads independently of collection/frame data. Recommendation payloads and public product thumbnails are smaller.
- Private derived frame previews share source downloads, use bounded five-minute caches, render off the async loop and offer 400px/1000px responsive sizes. Current signed ownership is checked before every server cache lookup.
- Recommendations briefly reuse ranked candidate IDs, while current ownership, catalogue eligibility and native Storefront availability remain checked. Two cards retain the existing smart rank. Obsolete requests skip the next Storefront query after edition changes.
- Two-line certificates replace divider punctuation with a line break and use a smaller, lighter athlete subtitle. The latest JPG badge/borders/Handcrafted placement are preserved. The entire title/number block is centred. Number allocation and existing issued assets are unchanged; no customer certificate backfill is part of this release.
- Photos retain the existing account submission route; video links to the storefront reviews form. Native edition browsing stays swipe-and-tap as the user selected. Orders remains separate from My Collection.

## Phase 4 diagnostics

Known read operations are timed in the native account: collection orders, bootstrap, review options, recommendations, frame pricing and paired-product reads. Reports are batched after two seconds, with at most 12 samples per batch and 24 samples per API context. Unknown operations/fields are not reported. Reporting failures are swallowed and never retry customer actions, create carts or submit reviews. The four-second fetch timeout bounds the reporting request after token retrieval.

The authenticated POST `/api/collector-vault/performance` requires the existing extension marker and session. It accepts at most 4096 bytes and exactly the whitelisted operation, a finite 0–120000ms duration and an `ok`/`error`/`aborted` outcome. A whole batch is validated before any sample is logged. No customer ID, order ID, title, address, message, file, URL or token is accepted in this schema or persisted by the reporter.

Server response preparation timings appear in `Server-Timing` on collection/bootstrap/review/asset responses and in `collection_perf` logs. Streaming file timing covers response preparation, not complete transfer. Frame and candidate cache logs expose only cumulative hit/miss/wait/failure/busy totals, never keys or cached content. The dedicated logger inherits Uvicorn's operational log handler. These are process-local diagnostics; no analytics database or paid monitoring service is added.

Operational review uses Render logs filtered for `collection_perf`, `collection_cache` and errors. Compare cold/warm preparation, client read durations, error rates and cache counters. Client timing samples reflect named operations, not full browser LCP/INP/CLS. Shopify's native worker does not expose the complete host page performance timeline, so no synthetic Lighthouse score or public SEO improvement is claimed.

## Verification and release sequence

The combined local account/certificate/cache suite passed 175 Python tests and 14 subtests; the native suite passed 45 Node tests. Project TypeScript, Shopify production build/configuration and topology checks pass. The compressed account bundle is approximately 18.7 KB. The broader existing Orders/Inbox release gate and the GitHub collection release workflow are required before production integration; their exact results and deployment IDs are retained in runtime release evidence.

The standalone Shopify Toolkit component validator is unavailable because its own installation lacks TypeScript. The actual project's compiler and Shopify build are the executable native validation gates. Older unrelated source-assertion/account-query failures remain documented in Phase 2; they were not rewritten to disguise regressions. Local browser previews with production credentials remain disabled.

Release sequence: commit only the reviewed task files, push the isolated branch, pass GitHub CI, integrate the tested revision without force-pushing, wait for the canonical Render deployment to become live/healthy, then run `shopify app deploy --path shopify_customer_account --allow-updates --no-input` for the existing configured app. This uploads the tested app/extension source and configuration; it does not remove extensions or change requested scopes. Verify live account display, frame selection and review-dialog controls without making a purchase or sending a real review. Record backend revision, app version, health and read-only live observations in `C:/Dev/SportsCaveWorktrees/.studio/runtime/20261123-9c2e1a01/`.

If backend deployment fails, retain the prior account app version and recover the existing service. Backend changes preserve old API defaults. A failure after the extension release can be recovered by releasing its previous app version and reverting only this release's commit; never reset unrelated work or recreate a Render service.
