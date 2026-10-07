# Wall Preview first-party engagement

## What changed
The deployed viewer previously emitted local/dataLayer events but did not use the standalone example analytics adapter in docs/storefront. Server capture confirmations still populated legacy metrics. Capture UUIDs now change for each intentional save, so using client_preview_id as a whole-viewer journey also split visits. Neither legacy confirmations nor unique write sessions imply that an opening event was observed.

The actual viewer now posts canonical events to the existing /api/wall-previews/analytics/events endpoint. The first CTA is observed before lazy viewer initialization. Open is a separate observation after the overlay becomes visible. Camera open follows successful video playback. Photo loaded follows successful image decode. Placement follows confirmation. ATC follows a successful Shopify cart response even if archive storage is pending. Close follows the existing close path.

wall_preview_session_id identifies one viewer visit and remains stable across all capture IDs and photo changes. visitor_id is a random sessionStorage identifier, separate from the existing private write capability; it is not a person/customer identity or fingerprint. No email, image, secret, or query-string/referrer query is included. Existing local and dataLayer events remain unchanged.

## Metrics
Performance uses only newly instrumented visits, not incomplete historical capture proxies. Each stage counts once per visit/product. Unique Clickers counts distinct anonymous browser-session visitor IDs with a CTA. Click to Open requires an observed click followed by an open in that same visit. Photos, Placements and ATCs require a prior observed open. Placement Rate and Preview to Cart use those opened visits as denominator. No denominator means a dash, not zero percent.

The selected date window applies to event timestamps. Product/device/photo-source filters apply to all metrics; the latest known photo source is resolved consistently across the visit so pre-photo clicks/opens can be included once a source is known. Clicks which never reach a photo source cannot be assigned to a camera/upload filter. Old raw events and capture journeys remain in Analytics details and are not backfilled into this cohort.

Active time is cumulative foreground interaction time, measured with performance.now(), excluding hidden documents, blurred windows, closed/backgrounded previews and time beyond 60 seconds without pointer/keyboard activity. A 15-second heartbeat runs only for open viewers. Unchanged snapshots are suppressed. Visibility loss/pagehide/close flush via sendBeacon (text/plain, avoiding an unload-time preflight), with keepalive fetch fallback. Snapshots use MAX per visit, never SUM. Average/median use visits with recorded duration snapshots; historical unknown durations are not zero-filled. Abrupt process/device termination can lose the final heartbeat interval; this is measurement, not a guarantee of delivery.

Events have immutable UUIDs. Bounded transient retries reuse exactly the same body/ID and respect Retry-After. The existing unique session/event-key index prevents duplicate ingestion. Separate ownership checks fence visits and capture identities. No analytics failure blocks camera, renderer, cart or storage.

## Deployment order
Apply the SHA-reviewed additive 20261006084655_wall_preview_engagement.sql migration through the existing deployment runner, then deploy backend/reporting before the updated Shopify JS asset. No old tables/history are deleted. Existing RLS/private read authorization is preserved. The Liquid wrapper and CSS do not change for this feature. No production deploy/write was performed during local validation.

## Local validation
178 Wall Preview Python tests, 4 migration connection tests and 13 Social Inbox tests passed. The dedicated analytics/engagement subset contains 15 tests, included in the Wall Preview total. JavaScript clock tests cover hidden/blur/idle time, resume, exact-ID retries and 429 cooldown. Real viewer desktop-upload/mobile-camera tests exercise the complete funnel. Existing completion tests passed 16 viewport/photo combinations; Inbox browser tests passed 14 responsive sizes. Python compile, Node syntax and deployment manifest READY checks passed. No production analytics/capture records were created.

## Files for this change
- shopify_theme/assets/sports-cave-wall-preview.js
- wall_preview_analytics.py
- wall_preview_analytics_api.py
- wall_preview_analytics_ui.py
- run_migrations.py
- migrations/20261006084655_wall_preview_engagement.sql
- tests/test_wall_preview_engagement.py
- tests/wall_preview_engagement.cjs
- tests/wall_preview_engagement_browser.cjs
- tests/test_wall_preview_completion.py
- tests/social_inbox_preview_app.py
- tests/social_inbox_ui.cjs
- docs/WALL_PREVIEW_ENGAGEMENT.md

Camera-open is observed when the embedded live video actually plays. Browsers do not expose whether a native camera/file chooser successfully opened; native photo input results are classified as camera without inventing that opening event.
