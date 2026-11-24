# OS reviews: provider retirement

24 November 2026, Australia/Sydney. Continuation of task `20261124-c419098d`.

## Confirmed production state

The product-title review count and bottom widget now use the same OS summary. A first-page preload updates the visible title and widget summary immediately, even while the widget is below the viewport. Previously the preload cached data without applying it until the widget approached the viewport. No polling, extra per-review queries or new visual design was introduced. Public totals change after a review is published, not while it is pending moderation. New page loads use the OS summary with its bounded 30-second cache; an already-open page is not a real-time subscription.

An isolated browser test changed the response from 209 to 210 on a new page load and confirmed that both counts changed before the review archive was rendered. The real storefront remains at **209**, approximately **4.82/5** (the compact title rounds to **4.8**).

Shopify displayed **You've successfully uninstalled Judge.me Reviews**. The owner separately confirmed the final notice about deletion of app-managed data and the developer's personal-information deletion request. OS review data, imported provenance and Dropbox media were preserved. No manual deletion of Shopify customer records or OS rewards was performed. The old unpublished theme remains a historical backup; using its former provider would require a fresh installation and coordinated request ownership.

The Shopify pixel disappeared after uninstall. Both the public product page and reviews page returned **zero** Judge.me/JDGM references in their HTML. Native media viewer sources still use `/reviews/media/` on the OS origin. The native form opened after uninstall, offered five stars by default, and its submission button was enabled. The photo carousel/viewer still opened correctly. Title and bottom summaries both showed 209.

Live runtime readback after the cleanup deployment confirmed:

- Native reviews enabled.
- Post Checkout ACTIVE, publication 8, three conditional review-request slots.
- Photo/video rewards enabled at 30% each.
- All 29 media records attached to published reviews copied to Dropbox; zero failed copies. The hidden historical video remains hidden.
- Retired provider credentials empty and zero pending/running legacy API-sync jobs.

## Removed integration

Removed the server API adapter, product-lookup credentials/cache, old account API delivery implementation, live-sync enqueue action, provider sync UI and network import worker branch. Cached account clients route through native OS ownership validation and Dropbox handling. Any obsolete queued provider job terminates safely with `provider_retired`, without making a request. Offline CSV imports continue.

Cleaned the live theme's old image URLs, disabled provider review sections/blocks, provider selectors/styles and jump-target fallbacks. Product thumbnails, review presentation and country ordering remain native and unchanged. The released account JavaScript and source map contain zero provider references. Retired credentials were cleared on the existing primary, webhooks and CRM worker services with merge-only configuration updates; unrelated secrets were preserved.

Historical source identifiers, imported metadata, immutable schema migrations and audit documentation intentionally retain the old provider name. Those records neither call nor depend on the uninstalled service, and retaining them protects deduplication, editorial ordering and the imported verification history. Original source URLs are provenance; displayed customer media is served from Dropbox-backed OS endpoints.

## Validation

- 140 focused review/account tests passed, plus 14 subtests, against a disposable local SQL fixture.
- Five browser tests passed: AU/US presentation, native public/buyer multipart forms and count synchronization before viewport entry.
- Ten lifecycle-publication tests passed, plus five subtests. The broader publication/timing run had 36 passes and one unrelated abandoned-checkout fixture failure: it lacks mocked Shopify trigger readiness. The timing/runtime/capability source and that fixture are unchanged by this release. This is not reported as a passing broad suite.
- Shopify Theme Check reported no errors in any of the 16 changed files. Existing unrelated `feature-rating.liquid` syntax and locale translation findings remain outside this release.
- Render topology validator passed; the canonical three existing services were retained.

Source cleanup release `e79dcb3967d45dcf2157c9e8ab2e70853b368d3d` was observed live on primary, webhooks and CRM worker. A final follow-up records proof, removes obsolete internal wording and retains the pre-existing heading appearance. Production review count was not inflated for testing; no real customer review slot, inbox send or coupon redemption was used as a synthetic test.

Evidence: `artifacts/native-review-launch/provider-retirement-audit.json` and `judgeme-uninstalled.jpg`.
