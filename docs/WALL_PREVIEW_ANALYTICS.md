# Wall Preview funnel analytics

## Implementation and rollout boundary

This change is local only. It extends the existing Render application, `wall_preview_events` ledger, CRM adapter and verified `orders/paid` attribution. It does not replace the image-storage route, create a service, publish a theme, send email or submit orders.

The complete Shopify visualizer source is not present in this repository. `docs/storefront/wall-preview-crm-v2.js` is the existing integration adapter, not the theme itself. The adapter is implemented/tested, but the new action hooks below must be wired into the actual theme before production camera/gallery/drag/scale/close counts exist. No production-theme UX claims are made from the synthetic hook tests. The user was asked for the source location.

Apply `migrations/20261006030857_wall_preview_funnel_analytics.sql` through the existing reviewed deployment runner before starting this code. The migration is registered with its checksum. It extends the existing table, permits anonymous events with no saved preview yet, expands the event check constraint, adds metadata/revenue columns and indexes, and keeps RLS with all public/anon/authenticated privileges revoked. Existing rows, routes, events and inbox workflows remain intact. No production migration has been applied.

## Events and exact integration points

All 19 requested canonical names are accepted, with `WallPreviewPurchased` strictly server-only. Existing `WallPreviewEmailCaptured` and existing saved-preview events are preserved.

Use the same `SportsCaveWallPreviewCRM(hooks)` instance and existing metadata/session/client identifiers. Add these calls at the current successful action handlers, without replacing those handlers or altering DOM/canvas/cart code:

| Existing action | Adapter call |
| --- | --- |
| Visualizer actually opens | `opened()` |
| Camera successfully opens | `cameraOpened()` |
| Gallery picker opens | `galleryOpened()` |
| Shutter capture succeeds | `photoCaptured()` |
| Uploaded image decodes successfully | `photoUploaded()` |
| Photo is ready for placement | `photoReady()` |
| Meaningful completed drag | `dragCompleted(cssPixelDistance)` (>=3px; first per journey only) |
| Selected frame actually changes | `frameChanged(selectedLabel)` after updating existing metadata |
| Selected size actually changes | `sizeChanged(selectedLabel)` after updating existing metadata |
| True-scale calibration begins/completes | `scaleStarted()` / `scaleCompleted()` |
| Quick-preview action used | `quickPreviewUsed()` |
| Popup closes | `closed()` |
| Reliable checkout-start signal with this line's attribution | `checkoutStarted()` |

Existing `newWallPhoto`, `placementChanged`, `confirm`, `download`, `share`, `cartProperties`, `addedToCart`, and email methods remain. Started is deduplicated when `newWallPhoto` follows `opened`. A second wall photo starts a new client preview as before. A confirmation retry at the same placement revision does not double-count. Download/share/ATC keep their existing authenticated CRM writes and also emit small anonymous-capable funnel events. Reporting avoids double-counting legacy server proxies when a matching browser event exists.

Do not call checkoutStarted on an arbitrary checkout button click. Wire it only to a verified checkout-start signal that retains the existing line properties. This optional signal cannot be wired or verified without the theme/checkout integration source. Purchases do not depend on it.

No SDK, pointermove tracking, image payload, new identity scheme or visualizer style changes are introduced. Analytics is fire-and-forget, catches synchronous/network errors, uses keepalive and a close-event beacon where available. No retry loop can block a visualizer action.

## API and access

- `POST /api/wall-previews/analytics/events`: anonymous, allowlisted storefront origin, bounded 8 KiB body, session-based in-memory abuse limit, allowlisted metadata, UUID event retry deduplication. Paid events/revenue cannot be posted by the browser.
- `GET /api/wall-previews/analytics/summary`
- `GET /api/wall-previews/analytics/funnel`
- `GET /api/wall-previews/analytics/products`
- `GET /api/wall-previews/analytics/events`

Reads require a current OS account/session with Social Media access, including session revocation/lock validation. Filters: start_date, end_date, product_id, device_type, capture_source. Default 30 days, bounded to 366 days. Event reads also allow preview_id and bounded limit/offset (maximum 200 per page, offset up to 10,000). Product table returns the top 100 products. UI uses the same server-side reporting service directly and caches aggregate reads for 60 seconds; Refresh clears it. No OS Shopify HTML scraping or analytics SDK is involved.

The random session remains the existing private preview write capability. It is sent only to the first-party backend and never returned by the analytics read endpoints or exposed in DOM events/dataLayer. No new IP/fingerprint collection or customer identity enrichment is added. Query strings/fragments are removed from page/referrer URLs; only the requested UTM fields survive. No wall photograph, email or name is accepted by the analytics cleaner.

## Purchase attribution and metrics

The already-HMAC-verified paid-order pipeline calls `wall_preview_crm_store.correlate_order`. It continues existing suppression and CRM purchase updates. New purchase evidence is uniquely keyed by Shopify order ID + line ID, so webhook retries cannot multiply revenue. Exact variant/product identity is checked. A client-only preview whose archive failed can still be attributed if persisted anonymous events match the purchased product/variant.

Revenue = Shopify line price × quantity − discount allocations, in shop/order currency. Order total is retained separately and is never summed once per attributed line. Missing monetary evidence remains unknown, not fabricated. Currencies are displayed separately, with no guessed FX conversion. Product rows sort by purchases, then attributed revenue. Refund/net-revenue reconciliation is not part of this change: revenue is paid attributed line revenue, not net after later refunds.

KPIs count unique preview journeys per stage; Unique Sessions counts the existing session ID. Funnel also displays actual event counts. Conversion/drop-off uses journeys with a subsequent next-stage event in the selected window, never division of unrelated event totals. Preview-to-ATC/purchase rates use the opened cohort. Purchases can be present without a tracked open in that window; no false rate is manufactured. Legacy server-created Started events are not treated as proven popup opens. Existing confirmed/purchase evidence remains usable, without inventing prior camera/drag events.

## OS

Order: Overview → Wall Preview Inbox → Create → Plan → Playbook → Tracking.
Overview adds only the 7-day Opens/ATCs/Purchases/Revenue module and an inbox link, retaining the existing daily overview content. Inbox adds date/device/source/product filters, nine metrics, funnel, products and interaction insights above the unchanged inbox controls/cards/workflows. Details adds Journey timestamps and Anonymous visitor when no existing identity is known. The existing signed-in identity and email information is reused, never guessed.

## Tests

With the local-only PostgreSQL fixture running (`node tests/crm_postgres_server.mjs`) and `CRM_TEST_POSTGRES=1`:

```
.venv/Scripts/python.exe -X utf8 -m unittest tests.test_wall_preview_analytics tests.test_wall_preview_crm_v2 tests.test_wall_preview_feature tests.test_wall_preview_identity tests.test_wall_preview_hd_send tests.test_wall_preview_hd_email tests.test_social_media_navigation tests.test_social_media_page -q
node tests/wall_preview_analytics.test.cjs
node tests/wall_preview_crm_adapter.test.cjs
```

169 Python/database tests passed. Node tests passed four anonymous camera/upload/mobile/desktop journeys, all action hooks, dedupe, privacy and outage isolation; the existing six adapter contracts also passed. Compile checks passed.

`tests/wall_preview_analytics_ui_fixture.py` on loopback port 8877 plus `node tests/wall_preview_analytics_ui.test.cjs`: passed 1920/1366/750/390/320px layouts, Overview link, unchanged inbox controls and anonymous Journey. External network was blocked. Screenshots: `test-results/wall-preview-analytics/analytics.png` and `inbox.png`.

## Files changed for this request

- wall_preview_analytics.py (new)
- wall_preview_analytics_api.py (new)
- wall_preview_analytics_ui.py (new)
- wall_preview_crm_store.py
- wall_preview_inbox.py
- social_media_page.py
- sports_cave_server.py
- run_migrations.py
- migrations/20261006030857_wall_preview_funnel_analytics.sql (new)
- docs/storefront/wall-preview-crm-v2.js
- docs/WALL_PREVIEW_CRM_V2.md
- docs/WALL_PREVIEW_ANALYTICS.md (new)
- tests/test_wall_preview_analytics.py (new)
- tests/test_wall_preview_feature.py
- tests/test_social_media_navigation.py
- tests/wall_preview_crm_adapter.test.cjs
- tests/wall_preview_analytics.test.cjs (new)
- tests/wall_preview_analytics_ui_fixture.py (new)
- tests/wall_preview_analytics_ui.test.cjs (new)
