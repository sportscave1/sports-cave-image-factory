# Product Upload saved WebP package

## Browser clipboard repair (local, pending release)

The reported browser failure was the direct WebView2-only bridge lookup: ordinary
Edge/Chrome/PWA pages have no `window.top.chrome.webview`. Installing helper v12
alone could not connect that page to the helper. No clipboard write was attempted.

The local repair adds a Product Upload-specific `sports-cave-files://webp` launch,
handled by helper v13. An authenticated same-origin request with Files permission
issues a four-minute, one-use capability for exactly the current upload/package.
No arbitrary paths or Dropbox credentials are passed through the URL. The helper
accepts configured trusted origins only and removes the capability fragment from
its displayed URL before claiming. Claiming cannot be repeated or raced twice.

The helper reuses the verified eight-file hydration and native FileDrop clipboard
service. Only its successful eight-file response can complete the operation.
The original page polls owner-authenticated completion, shows Copied for two
seconds, then restores its label. Every later click creates a fresh operation;
the hydrated cache can be reused but cannot prevent another clipboard write.
Failed/partial writes never report Copied. Cancel, source/package changes and
unmount revoke pending requests. A visible Open clipboard helper link supports
browsers requiring an explicit external-application gesture, with Cancel copy
available while waiting. The existing exact-file fallback remains secondary.

Verification: 27 clipboard/package/real-entrypoint tests pass. Native helper build
and payload checks pass, including compiled trusted-origin protocol validation.
Two Node checks exercise first copy and repeated copies, independent feedback,
partial counts, native errors, cancellation, stale packages and listener cleanup.
Actual browser protocol approval and an eight-file paste in ChatGPT remain
unverified. Web changes and helper v13 must be released together; the installed
v12 helper and deployed service are unchanged by this local repair.

Released with the Edition Ops mapping update from the existing PRODUCTS task,
19 October 2026, with explicit user authorisation. Code is pushed to the task branch
and main; Render uses the existing sports-cave-os service. Windows helper version
12 is installed with the existing Dropbox root and trusted origins preserved.

## Behaviour

- Save all has inline Saving / green Saved feedback. Saved requires the entire
  receipt and a source/category/name/file-stamp match. Numbered destinations
  display the actual saved product-folder name. Upload changes revoke the saved
  handoff; beginning another save invalidates outstanding native transfer grants.
- The handoff automatically follows successful saving. Open folder and Continue
  to Shopify are removed. The latter only caused a rerun; save completion already
  does that and persists the prerequisite through the existing bind_export.
- Eight receipt-derived WebPs appear in canonical gallery order. Their source
  is the exact export fingerprint and confirmed IDs/revisions/hashes, not folder
  browsing. Complete receipt validation includes the additional export formats.
  Existing exports, encoding, collision handling and mapping remain in place.
- Initial images use Dropbox's small-thumbnail service without original fallback.
  Opening an image streams only its pinned saved revision. The original API checks
  the upload and package version; stale URLs fail closed.
- Adjacent Copy all WEBP files / Copy upload prompt controls retain independent
  two-second feedback. Prompt generation retains Draft/Live/Update and the actual
  upload-operation correlation block. MAP and mapping-only refresh remain intact.

## Native clipboard

The existing trusted Windows WebView2 host already provided file-drop clipboard
support, authenticated short-lived transfer grants, hydration and a disk cache.
Generic copyFile can reuse local paths without hashing every byte, so the new
capability does not advertise success through that older path.

Helper version 12 advertises productUploadWebp. Its copyWebpPackage action:

1. Requires the server-created, owner-authenticated product_upload_webp grant.
   Client-supplied arbitrary paths are not accepted by the Product Upload API.
2. Uses the existing pinned-revision download and full Dropbox content-hash/size
   verification for all eight files, including local synced files/cache hits.
3. Materialises exact filenames in a package-specific WEBP lease directory;
   originals are unchanged. Files remain available under the existing cache
   retention policy; a three-day lease is written (normal cleanup is later).
4. Revalidates the current persisted upload/package after hydration. Only then
   writes Windows FileDrop through the existing retrying SetClipboardData helper.
   The browser requires a successful native response with the complete count.
5. Cancellation, stale component generations and iframe removal cancel pending
   native requests and clear feedback. Errors identify the affected file.

The secondary Select saved files action can reveal the exact materialised folder
in the updated host. In a regular browser it exposes only the eight exact saved
file downloads, with instructions to select them in ChatGPT's attachment picker.
It never calls links, converted images, or a partial transfer “Copied”. A web-only
browser cannot supply the native multi-file clipboard through this integration.
The old URI helper is deliberately not used: it has no authenticated completion
receipt for this operation.

The helper now includes a Product Uploads navigation button. Its restricted
--product-uploads[=upload-UUID] entry point opens only the configured trusted
origin and retains normal server authentication/ownership checks. Regular browser
windows do not expose this native bridge and retain the honest attachment fallback.

Older uploads recover their package from their own unique completed save receipt
and saved role/filename context. Ambiguous, incomplete or changed receipts fail
closed; no folder search or new export is performed.

## Verification

- 14 new package tests: exact order, missing/extra/changed files, stale source and
  package, native grant identities, thumbnail-only loading, pinned original fetch,
  actual Streamlit inline Saved control, numbered destination, invalidation, and
  all three prompt modes with the real correlation composer.
- 19 desktop-helper tests pass across focused runs, including Windows compilation,
  background-host startup and a real Windows FileDrop object containing all eight
  original WebP filenames. The latter does not write the user's clipboard.
- 39 existing mockup/mapping tests, 7 real __main__/Streamlit entrypoint tests,
  and 3 focused native-transfer tests (+3 subtests) pass.
- Node saved-package lifecycle, original copy feedback, selection state and
  mapping lifecycle checks pass. Tests cover count mismatch, rejection, retry,
  independent timers, restart at 2 seconds, stale completion and unmount cleanup.
- Desktop browser fixture uses synthetic artwork and real component/API code.
  Confirmed eight ordered thumbnails, adjacent actions, honest bridge-unavailable
  fallback, exact download list, prompt Copied/reset, and a clicked 1024px original.
  Provider log: eight thumbnails, zero originals until the explicit click, then
  one black-frame original. Desktop and 640px layout at 150% CSS scale were
  inspected without overlapping controls. This is a fixture, not production.

Release checks: 22 package/real-entrypoint tests pass together, 19 desktop-helper
tests pass, and package/mapping/selection JavaScript checks pass. An expanded
mixed run had 76 passes and three Streamlit form-context failures; the seven real
entrypoint cases pass in a fresh process and alongside the package tests. The mixed
test-process interference has not been resolved and is not a live-runtime result.

Not verified: one native clipboard paste attaching all eight images in the actual
ChatGPT composer. The installed native host opened Product Uploads signed in, but
Windows Computer Use stopped before the paste because it could not confidently
determine the desktop browser URL for its policy check. Real Dropbox save/copy and
live Edition Ops mapping were not exercised. Do not describe ChatGPT acceptance as
passed. No ChatGPT message was sent.

Local screenshot: output/product-upload-package/desktop.png (synthetic fixture).
Run fixture: python -m tests.fixtures.product_upload_package_ui.

## Files for this change

product_upload_package.py; product_upload_api.py; product_upload_intake.py;
product_upload_mockups.py; product_upload_export.py; product_upload_outputs_ui.py;
product_upload_mockups_ui.py; components/product_uploads/{index.html,app.js,package.js};
files_upload_api.py; desktop_helper/{SportsCaveFilesDesktop.cs,Install.ps1};
tests/test_product_upload_package.py; tests/test_product_upload_package.cjs;
tests/test_product_upload_state.cjs; tests/test_desktop_helper.py;
tests/fixtures/product_upload_package_ui.py; this document.

## 2026-10-19 native preparation release (helper v14)

The installed helper recorded HttpRequestException before copying any files.
An isolated CodeDOM-built .NET probe reproduced the transport failure: its default
SSL3/TLS1.0 failed the service HTTPS handshake; explicitly selecting TLS1.2 returned
HTTP 200. The helper now selects TLS1.2 without weakening certificate validation.

The saved receipt's exact WEBP directory is listed by folder ID across all pages
and checked against the displayed eight-file receipt. A scoped native session
prepares these files without touching the clipboard. Explicit Copy All commands
reuse the prepared files, verify their bytes and current operation, write FileDrop
on the interactive STA dispatcher, then read back the exact eight paths. Completion
is acknowledged only afterward. A new preparation revokes old sessions; errors,
expiry, disconnection and cancellation remain visible and retryable.

The native helper must be v14 for this release. The protocol may require the
browser's normal external-application approval; the connection link remains visible
until the helper connects. No unauthenticated local server was added.

Release checks: 47 focused Python tests (including real Windows compilation and
real application entrypoint), both updated JavaScript lifecycle suites and Render
topology validation passed. Actual ChatGPT eight-attachment paste and ready-state
latency remain unverified. Windows automation stopped on browser URL policy during
the preceding turn; no end-to-end success is claimed. No live product writes were
performed. Fixture tests use synthetic assets and an isolated compiled helper.
