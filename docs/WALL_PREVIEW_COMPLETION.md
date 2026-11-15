# Wall preview completion patch

Local patch for the existing `snippets/sc-wall-visualizer-v1.liquid` asset, read from published theme **Symmetry 9 Gifting** (188890644787), 2026-10-06. Source asset checksum supplied by Shopify: `d9cb97ca15d76532969c669f1b0e845d`. This change has not been uploaded to Shopify or deployed to Render. Re-read/compare the live asset before applying to avoid overwriting subsequent theme edits.

## Behavior

- Existing confirmation becomes “✓ Your wall preview is ready”, politely announced and automatically faded/hidden after 1.8 seconds.
- PLACE and Download reuse `ensureSavedPreviewAsset`, `buildCompositeCanvas(true,3200,8000000)`, `canvasToBlob(...,'image/jpeg',.92)`, and the same cached Blob. The renderer is unchanged. Share continues using its existing cached File path.
- Placement exports are captured immediately. The promise queue preserves action order even if image rendering or retries finish out of order. Closing does not cancel a captured save or restore stale UI state. Failed requests have the existing three bounded retries; another PLACE/Download is the next browser retry opportunity. Navigating away before the server accepts a request cannot guarantee delivery.
- Existing session ID storage is reused; legacy `session-<UUID>` prefixes are normalized to the same UUID. Existing client preview IDs now use secure UUID v4 values required by the already-existing anonymous API. A new photo starts a new preview; repeated placements of that photo update it.
- Existing `/api/wall-previews` ingestion, database transaction, archive job and Dropbox worker are reused. One client preview row, one stable Dropbox path, versioned durable job, overwrite mode. No new service, queue or migration.
- `finished_composite=1` preserves validated, metadata-free canvas JPEG bytes and dimensions. Private metadata on other input is still stripped; legacy callers retain their current 2400px cleaning path. Existing origin, size, decoding, rate-limit and session ownership checks remain.
- Only Download supplies explicit `image_reuse_allowed=0/1` with `reuse_consent_source=wall_preview_download_checkbox`. It updates existing `marketing_permission`, `image_reuse_consent_at/source` and legitimately supplied contact fields on the same record, including when image deduplication makes the upload a no-op. Automatic PLACE does not approve image reuse. A genuinely new composite clears previous approval. No marketing subscription or email job is created by this permission update.
- Keep browsing is a muted 24px-minimum tertiary target, only after confirmation; it calls unchanged `closeDialog`, restoring the underlying page, scroll and focus. Hidden at heights <=600px. Footer clearance is measured when visible. The existing fitted desktop layout is also used for short landscape screens, without its old 520px minimum-height assumption. No rendering/scale math changes.
- Existing CustomEvent/dataLayer events remain; requested lower-case completion aliases use that abstraction. No image or contact identity enters these new events. Existing server event requests use the existing capability header and accepted event-name/id contract.

## Local validation

Use the existing disposable PostgreSQL fixture (`node tests/crm_postgres_server.mjs`, port 8873). Never point tests at production.

```powershell
$env:CRM_TEST_POSTGRES='1'
.venv/Scripts/python.exe -X utf8 -m unittest tests.test_wall_preview_completion tests.test_wall_preview_crm_v2 tests.test_wall_preview_feature tests.test_wall_preview_hd_send tests.test_wall_preview_hd_email tests.test_wall_preview_analytics tests.test_wall_preview_identity -q
node tests/wall_preview_completion_queue.cjs
node tests/wall_preview_completion_ui.cjs
```

Browser tests need Playwright and local Edge; set NODE_PATH to the installed runtime modules if needed. They render the actual snippet markup, CSS and JS with fixture Liquid product values and mock every network request. Test images are generated locally. They exercise upload, drag, PLACE, toast, exact Download/save bytes, unchecked permission, failure isolation, close/scroll restoration and reachable controls across portrait phones, short landscape, tablets and desktop, with portrait and landscape room photos. Screenshots go to ignored `output/`.

These are browser emulations, not physical iOS/Safari camera, notch or browser-toolbar certification. Camera, rendering, variant, cart, Share and close functions are additionally checked byte-for-byte against the published source. Native Share and real Shopify cart/provider writes are not executed.

## Release dependency

Deploy the backward-compatible backend changes before uploading the local theme snippet. Existing durable archive-worker configuration and credentials are reused. No credentials belong in the theme. A local repository commit alone does not publish this Shopify asset.
