# Catalogue product picker: local implementation and verification

## Causes found

The existing picker already paginated a lightweight synced `shopify_products` SQL index, but then immediately called `Catalogue.resolve` for every result row. Each new page/search waited for contextual Shopify pricing and Edition Ops data for products that might never be selected. Reopening discarded the page and repeated this work. Checkbox selection itself already reused the current page and made no requests.

Catalogue option events reran the enclosing Campaign workspace, including settings/render configuration and header/footer metadata reads, then reran again to acknowledge the component event. Product reads were already guarded for unchanged selections; the avoidable cost was parent-workspace work. Rapid queued settings also used an old settings object and could overwrite earlier toggles.

## Implementation

- Added a compact Collection selector beneath Search. Default: All collections. Collection labels are real Shopify data, alphabetized, with manual/smart collections included (no type restriction).
- Collections use the existing authenticated Shopify adapter and bounded cursor pagination (100/page, maximum 5,000); incomplete responses fail safely rather than publishing partial lists.
- All collections browsing keeps the existing read-only SQL product index. A selected collection uses one lightweight paginated Shopify `products` query with `collection_id`, quoted title/handle search and optional `status:active`. No per-product membership requests or separate catalogue mirror.
- Search submits on Enter/blur or Search; it does not request on every keystroke. Changing Collection or Active only updates the dialog immediately. Selection basket is independent of filtered rows and persists across filters; Add selected commits it.
- Picker rows now load only title, ID, handle, status and thumbnail. Pricing/edition summaries remain in the email composer/output; they are no longer resolved for every picker row. Rich facts resolve in one batch for selected IDs on Add selected. The loaded-selection marker prevents a second automatic resolution immediately afterward.
- Picker thumbnails use 80px Shopify CDN transforms; final email images are unchanged.
- New `crm_picker_cache.py` reuses the bounded DisplayCache implementation: 10-minute TTL, 256 entries / 8 MiB, account/connection/filter/page keys, striped locks for single-flight loading. Errors retain previously cached data with a compact notice and 60-second retry backoff. Cache is process-local and display-only; no new database/schema.
- Composer/preview now share a smaller Streamlit fragment. Catalogue events do not rerun the outer settings/brand-template/recent-history/top-send controls. The inactive Campaign Settings tab does not run subscriber or timing controls. Independent existing count hydration is unchanged.
- Presentation changes reuse loaded product snapshots and the existing safe preview cache. No product/customer/edition calls are made for Price, Limited to or Remaining. The existing component acknowledgment still uses two composer-fragment passes per event; the full page/workspace does not rerun. Picker filter/selection events use one dialog pass.
- Rapid settings changes merge pending changes instead of losing earlier toggles. CTA typing has a short 180ms debounce with immediate blur commit.
- New Catalogue defaults: image/title/limited-to/next/remaining/CTA ON, **Price OFF**, CTA **Claim Your Edition**. Only the new-section constructor changed. Existing saved values, selected products, columns, CTA and renderer remain intact.

Shopify operations validated against the installed schema (read_products). The existing API/auth connection is reused. References: [collection filter](https://shopify.dev/changelog/posts/new-collection_id-filter-added-to-products-query-filters), [collections](https://shopify.dev/docs/api/admin-graphql/2026-01/queries/collections). The supported featuredImage field is deprecated in the latest schema; no API version change was made.

## Measurements

Controlled local Streamlit AppTest profile, two fixture products, injected 80ms index/collection responses and 160ms combined rich facts/edition work. These are not live-store or browser network latency claims.

| Operation | Before | After |
|---|---:|---:|
| Cold picker open, including framework overhead | 606ms | 509ms, including new collection list |
| New search | 249ms | 88ms |
| Select/deselect | 6.47ms | 5.99ms |
| Cached reopen | not recorded | 148ms, zero data calls |
| Price render | not recorded | 2.72ms, zero data calls |
| Limited-to render | not recorded | 2.83ms, zero data calls |
| Remaining render | not recorded | 2.39ms, zero data calls |

Before: each cold open/search made one SQL index request plus one batched Shopify facts request and one Edition Ops read for all visible rows. After: All collections open makes one cached SQL index read plus a cold collection-list request (one per 100 collections); search makes only a cached index read. Selected-collection pages make one Shopify products request per uncached page. Cached reopen and product checkbox clicks make zero data requests. Add selected resolves only chosen IDs. Collection-switch end-to-end timing was not recorded; behavior was verified in browser and tests. No numeric before/after toggle-to-browser-paint claim is made.

Raw profiles: `tests/fixtures/catalogue-picker-before.json`, `catalogue-picker-after.json`. Reproduce after with `python tests/profile_catalogue_picker.py`; it uses fixtures only.

## Tests and browser verification

- Full CRM suite: **277 tests passed**.
- Email suite: **144 run, 143 passed, 1 skipped**.
- Final focused picker/modular/rendering suite after the selected-facts reuse fix: **36 passed**.
- JavaScript checks passed: ordering/pointer boundaries, acknowledgments/queues, rapid setting merges, CTA debounce/blur.
- Python compilation and `git diff --check` passed.
- Seven new Python tests cover defaults/backward compatibility, collection pagination/cache, combined query filters, no N+1, TTL/concurrent refresh/stale fallback, safe thumbnails, dialog selection persistence/deferred facts, and presentation rendering without product reads.
- Local actual UI tested at **1440×900 and 1920×1080** with a fixture Shopify adapter and disposable SQL. Checked collection search, Active only, selection/deselection, Add selected, close/reopen persistence, repeated presentation toggles, columns, CTA, desktop/mobile preview. No layout errors remained after correcting the fragment boundary.
- Browser verification found an external-container fragment error in an intermediate implementation; that approach was removed. Final implementation uses one shared composer/preview fragment. No production code timing/debug logging was retained.

Screenshots:
- `C:/Users/hello/.codex/visualizations/2026/09/27/01a0e4de-ea00-7bd1-aac3-7f4691e4e95f/catalogue-picker-1440.png`
- `C:/Users/hello/.codex/visualizations/2026/09/27/01a0e4de-ea00-7bd1-aac3-7f4691e4e95f/catalogue-mobile-1920.png`

## Files

Runtime: `crm_catalogue.py`, `crm_picker_cache.py` (new), `crm_section_ui.py`, `crm_middle_sections.py`, `crm_campaign_page.py`, `components/crm_sections/composer.js`.

Verification: `tests/test_crm_picker_performance.py` (new), `tests/test_crm_modular_catalogue.py` (explicit legacy fixture settings), `tests/test_crm_sections_component.cjs`, `tests/catalogue_preview_app.py`, `tests/profile_catalogue_picker.py` (new), the two profile JSON files, this report.

## Safety and approval

CRM_MARKETING_ENABLED remains OFF. No emails sent, no Shopify product/collection or Edition Ops writes, no migrations, no send/consent/unsubscribe changes. No commit, push or deployment was performed by this agent. Git advanced externally to `531f0ae` (previous Segment performance work) during this task; this task's remaining code changes are local. Ready for Nathan's local testing and approval.
