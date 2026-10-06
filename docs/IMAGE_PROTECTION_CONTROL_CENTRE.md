# Image Protection control centre

Reuses the isolated storefront implementation from `9f46399`, after the mixed
`c599888` security work. No OS sessions, capture exclusion, auth gates or security
tables are restored. Main navigation now exposes the existing admin-only route
below Email. Settings remain in `app_settings.storefront_image_protection`;
legacy boolean values survive, new scope defaults are merged on read. No migration.

The existing server routes serve `/storefront-protection.js` and
`/api/storefront-protection/config` at
`https://sports-cave-image-factory.onrender.com`. Config is allowlisted, cached
60 seconds in process / 30 seconds HTTP, with ETags. One request per page load;
refresh existing pages after settings changes. Failures disable deterrence for
that load. Only the settings screen or public endpoint reads protection settings.
Admin changes use the existing activity log; an audit outage is logged separately.

Scopes: product/search/quick view, collection, homepage, Wall Preview. Native
context menu/drag/copy/save shortcuts, selection, WebKit callout and print are
targeted to media. No click, pointerdown, pointermove or touchmove interception.
Observable PrintScreen only displays a notice; it cannot block OS screenshots.
On-screen watermark text/opacity/position and separate Wall Preview watermark
are optional and default off. No source/composite/download pixels are changed.
No observer runs with watermark off. With watermark on, only added subtrees are
examined; no recurring document scans. No polling, SDK, customer telemetry or PII.

Installation: one deferred loader before `</body>` in the verified unpublished
Sports Cave DEV — Codex theme `189335863603`. Never publish it or edit MAIN
Symmetry 9 Gifting `188890644787`. The admin verification button checks the DEV
identity, loader and config reachability on demand; it does not invent heartbeat
or per-device execution claims.

Image delivery review: exports cap at 1600px, previews at 900px and Wall Preview
requests 2000px CDN images. Current gallery links request 5000px. Existing
Shopify originals remain publicly accessible; this change does not alter media,
master files, SEO markup or gallery quality.

Local validation:
- Image Protection Python: 14 passed, including legacy settings, admin boundary,
  safe fields, ETag, fail-open, UI and lazy OS startup.
- Accounts: 79 passed; startup scope: 6 passed.
- Top bar: 20 passed, one pre-existing missing `resetInitialSidebarScroll`
  assertion against the unchanged top-bar HTML.
- Wall Preview Python: 5 passed, 3 disposable-DB tests skipped.
- Storefront Chromium: 131 assertions, five widths, no runtime errors; config
  failure, independent scopes, dynamic media, print, forms, navigation, watermark
  default/off and duplicate-install guard included.
- Protected Wall Preview: 16 upload/placement/download/close journeys across
  mobile portrait/landscape, tablet and desktop. Network/storage fully mocked.
- Fake-camera Chromium mobile journey: launch, shutter, preview and CTA passed.
- 1000 delegated context-menu events: approximately 2.8ms locally; script 8116
  bytes at measurement. This is not a field Core Web Vitals measurement.
- Shopify Liquid validator: valid, expected external-CDN performance warning.
- Python/JavaScript syntax and Render topology validation passed.

Physical iOS/Samsung devices and native Safari/Firefox are not available here.
WebKit long-press remains best effort, not a guaranteed block. No true screenshot
protection claim is made. Combined Streamlit tests have existing process-global
form contamination; the focused suites were also run in separate processes.

Deploy only the Image Protection file allowlist. The unrelated uncommitted Inbox
work and its migration must remain local and excluded from this deployment.

## Deployment and DEV verification — 6 October 2026

Backend commit `0dfdd5eb6718a862233b41da77da8a90be4987f5` is live on
`sports-cave-os`, deploy `dep-db29v6bl550s73c6qcsg`. Public JavaScript matched
local content exactly; config returned 505 bytes with ETag and Wall Preview flags.
Only DEV `layout/theme.liquid` gained one loader line. Final API read-back matched
intended content and MAIN layout remained byte-for-byte unchanged; DEV unpublished.
The admin verification helper confirmed DEV loader and config reachability.

Actual DEV browser: homepage/collection/mobile artwork protection, right-click
notice, synthetic room upload, drag, PLACE success, Add to Cart/cart drawer tested.
The single cart item was removed; no checkout/order was submitted. Synthetic
placement tests exercised the existing background capture path. No real customer
image or identity was used. Mobile portrait/landscape had no horizontal overflow.

Download end-to-end is NOT signed off on actual DEV: the button did not open its
sheet in this browser. The same behaviour was reproduced after completely removing
the protection loader (zero script elements), including after PLACE. The loader
was restored and verified. DEV has an older visualizer than the reviewed local
widget, including its older queued-as-saved message. No visualizer source was
changed under this task. The current local widget passed all 16 protected journeys,
including successful downloaded-file bytes and repeated downloads.

The actual store also logs an unrelated `boostymark-regionblock` extension
`Unexpected end of input` error, present with protection absent. No protection
script runtime error was observed. Native Safari, Firefox, Samsung Internet and
physical iOS/Android testing remain unperformed. Do not describe this as full
cross-browser or real DEV Download sign-off.
