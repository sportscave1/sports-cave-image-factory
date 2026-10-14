# Files Performance V2 — isolated implementation and acceptance

Date: 14 October 2026. Worktree: `C:\Dev\SportsCaveWorktrees\sports-cave-files-performance-v1`.
Branch: `codex/files-performance-v1`. Studio task: `20261014-50508219`; owner: `codex/files-performance-01a1391d`.
Baseline: `823a19666e9d69a75b6c89b022ceb549cc2c1b4c`.

The implementation is ready for isolated code review and later integration testing. **It is not a claim of completed live Dropbox acceptance.** No suitable authorised non-production provider environment was available for this run. The user authorised synthetic tests instead. No production credentials, customer files, Dropbox mutations, production server startup, deployment, push or V11 changes were used.

## Evidence and root causes

The browser benchmark loads the actual Files, viewer and launcher HTML in Chrome, compares it with the baseline from Git, intercepts every request, and blocks other hosts. The Orders test uses the unchanged production Files-overlay installer in a synthetic Orders page. Python tests exercise actual API handlers and cache/concurrency code with mocked provider/auth dependencies and outbound sockets denied.

Measured application causes:

- Large folders rebuilt every row. At 2,000 entries, baseline had 16,120 DOM elements and a 53.2 ms synchronous rebuild, exceeding a 16.7 ms frame budget. Repeated sorting and rebuilding also delayed cached navigation.
- The viewer requested the original image before showing artwork. A generated 7,000 × 5,000 JPEG padded to 35 MiB took 516 ms to become usable in this local fixture, versus 77 ms for a 37,378-byte representation. These timings include mocked transfer delay and browser processing, not Dropbox service latency.
- Warm launcher clicks navigated the existing window again and caused another listing request. The updated launcher focuses it without reloading.
- Source tracing and request assertions identified extra viewer folder listings despite Files already holding the metadata, and exact-file flows that waited for folder pagination before selection.
- Concurrent cold connection setup and paginated listings lacked shared completed-page results. Request-count tests now establish single-flight behaviour and idempotent cursor replay.
- Thumbnail generations could reset counters while aborted requests still completed. The scheduler now keeps a real concurrency bound and avoids stale completions deleting newer tasks.

No measured claim is made about actual Dropbox latency, Supabase query duration, production authentication cost or production backend CPU. `Server-Timing` now exposes auth, connection, listing, formatting and JSON work for future authorised tracing; previews expose representation latency. Authentication remains enforced on each API request.

## Major changes

1. Preserve the existing shell, toolbar, breadcrumbs, Windows appearance and Orders overlay. Metadata loads asynchronously; partial listings remain usable and incomplete/error states stay visible.
2. Virtualise all five folder views above 200 entries, retain row identity during pagination, reuse an `Intl.Collator`, and render only the viewport plus overscan. Keyboard navigation can reveal offscreen items.
3. Preserve scroll, selection and focus across cached Back/Forward navigation. Cancel obsolete navigation and prevent older completions restoring the wrong folder or deleting a replacement request controller.
4. Deduplicate connection setup, complete folder listings and individual pages; share completed page results, bind cursors to their cache scope and reject obsolete responses after mutations. Retain the existing 500-entry production page size to avoid multiplying remote round trips.
5. Resolve saved file IDs directly through a new backward-compatible `/api/files-resolve` endpoint. Validate staff access, root scope, exact ID and optional revision before showing the selected file; load surrounding folder contents afterwards. Both saved Edition JPG and linked PSD Files flows benefit. Existing edition-specific download routes remain intact.
6. Add opt-in small/screen preview representations to the existing preview API. Preserve its legacy original response for existing clients. Browser previews request a small representation first; full-resolution raster transfer requires `1:1 Actual` or Download. No automatic original fallback and no layered PSD decoding.
7. Cache preview bytes by user, connection, path, revision and size, with bounded memory, negative-result caching, concurrent request sharing and mutation invalidation. A quick cached grid thumbnail can appear while the larger preview loads. Blob caches are bounded, short-lived and released; API responses remain private/no-store.
8. An explicitly requested original raster stream can seed a small server preview from those same bytes. It uses one nonblocking decoder slot, a bounded temporary spool, a 40-megapixel decode ceiling and best-effort cleanup. It never downloads a second original or changes artwork. A 35 MiB fixture verifies byte-for-byte streaming and subsequent cached preview access.
9. Lazy-load visible JPG/PNG/WebP thumbnails, retain stable icons while loading/failing, cancel offscreen work and cap live browser requests at four. Keep PSD Photoshop icons; do not download PSDs for grid thumbnails.
10. Coalesce search rendering to animation frames, avoid unnecessary DOM replacement, guard repeated download/rename/new-folder submissions, preserve download targets across delayed starts and invalidate folder caches after uploads even when the user has navigated elsewhere.

Cache freshness remains bounded, not real-time: existing server folder TTL is three minutes, page results two minutes, browser preview blobs 30 seconds, ordinary provider preview bytes 30 seconds. Explicit-original derivatives keyed by revision can live 30 minutes; unversioned derivatives only 30 seconds. Local mutations invalidate affected caches; external Dropbox mutations can remain visible until expiry or Refresh. Caches are process-local and do not constitute a new storage provider.

## Before/after measurements

Raw samples: [metrics.json](files-performance-v2-evidence/metrics.json). Milliseconds below are **p50 / p95**, six samples per folder variant and four per image variant. With such small samples, p95 is effectively the slowest sample, not a production percentile estimate. Folder fixtures use a fixed 30 ms listing delay; image fixtures use 40 ms. The render benchmark supplies the selected folder's complete metadata to isolate rendering cost; a separate multi-page test validates incremental behaviour.

| Action | Before | After |
|---|---:|---:|
| Cold 500-entry folder, first usable | 128 / 144 | 94 / 95 |
| Cold 2,000-entry folder, first usable | 250 / 258 | 102 / 106 |
| 2,000-entry shell DOMContentLoaded | 19.4 / 25.9 | 23.9 / 24.2 |
| Cached 2,000-entry folder | 129 / 147.3 | 6.8 / 7.1 |
| Uncached folder navigation, 2,000 entries | 290 / 303.9 | 53.6 / 62.5 |
| Back, cached folder | 148.3 / 153.7 | 5.4 / 5.9 |
| Forward, cached folder | 131.3 / 148.7 | 5.0 / 5.5 |
| Synchronous 2,000-entry rebuild | 53.2 / 56.3 | 1.5 / 1.7 |
| Selection handler, 2,000 entries | 1.8 / 2.2 | 0.3 / 0.3 |
| Search render, 2,000 entries | 11.4 / 12.5 | 1.5 / 2.2 |
| Cold image with available representation | 516 / 538 | 77 / 78 |
| Same image redisplayed in open viewer | 12.5 / 16 | 0.7 / 1.0 |

Main launcher click-to-shell was 95 → 90 ms in one sample (both variants use the updated Files shell to isolate launcher behaviour). Warm launcher reopen made 1 → 0 listing calls. The small shell parse-time increase above is reported rather than hidden; usable listing and navigation improve substantially.

At 2,000 entries, rendered rows fell from 2,000 to 56 and total DOM elements from 16,120 to 568. Chrome JS heap at the benchmark checkpoint fell from 6,252,336 to 3,834,264 bytes (about 39%); cumulative script duration for the measured page scenario fell from 69.42 to 12.90 ms. These are CDP measurements, not process RSS or production server CPU. Updated synthetic scroll frame intervals were 16.7 / 16.8 ms; no baseline scrolling trace or GPU/compositor guarantee is claimed.

Thumbnail acceptance requested 57 small assets for two distant viewports out of 1,000 files, with four live browser requests maximum. The mock server observed five outstanding responses including already-aborted requests; abort does not guarantee a provider stops work. A paired baseline thumbnail latency/count measurement was not collected.

Exact saved Edition selection appeared in 91 ms in the synthetic Orders overlay, before folder pagination completed, with zero preview/original transfers. Closing Files preserved the Orders filter. No paired baseline timing is claimed for this scenario.

## Provider requests and preview limitations

Verified request effects, using mock call counters:

- Reopening the same live Files popup: no extra listing.
- Opening the viewer from Files: no second folder listing when metadata is supplied.
- Exact-file resolution: one metadata lookup, no folder scan or content transfer to select it; surrounding browsing still lists the folder in the background.
- Six concurrent identical representation requests: one provider thumbnail call. Four concurrent identical page requests: one provider page call; cursor replay does not advance again.
- Cached/same-viewer redisplay: no new preview fetch. Initial updated preview requests a small representation; an explicit Actual action makes the original request. The raw image request totals are eight after versus four before because the after test additionally exercises Actual once in each of four samples; this is not a request regression for preview-only use.
- Ordinary errors no longer trigger connection refresh and duplicate listing retries. Actual authentication errors retain a single refresh/retry path.

**Critical external limitation:** Dropbox documents thumbnail conversion only for supported raster types and files at most 20 MB; PSD is absent from the supported-format list. See [official Dropbox SDK thumbnail documentation](https://dropbox-sdk-python.readthedocs.io/en/latest/api/dropbox.html#dropbox.dropbox_client.Dropbox.files_get_thumbnail). Therefore the mocked 35 MiB → 37 KB representation benchmark does **not** demonstrate that Dropbox can generate that representation. There is no approved derivative store in this checkout. For an unsupported cold large JPG, the viewer explains that a small preview is unavailable and offers explicit full-resolution inspection/download. A completed explicit raster inspection can seed a bounded derivative for later views. This still cannot guarantee a fast first cold preview for every 35 MB JPG. PSD preview is best effort only; native Open/Download remains the reliable supported route. No claim is made of fast cold previews for all 100–300 MB PSDs.

## Acceptance coverage

| Journey | Verification and boundaries |
|---|---|
| 1–2 Main Files click and popup shell | Actual launcher click/popup; shell before remote completion; warm focus reuse |
| 3 Authentication/connection | API permission denial, fresh auth on cache hit, context single-flight and retry tests; real provider latency unmeasured |
| 4–5 Initial folder/names | Cold 500/2,000 metadata browser runs; progressive 100-item fixture pages usable before completion |
| 6 Icons/thumbnails | Real grid icons, visible-first lazy requests, failure fallback, bounded concurrency and cache unit tests |
| 7–10 Folders/nesting/return/breadcrumbs/history | Rapid navigation, stale-response cancellation, nested paths, Back/Forward, preserved scroll/selection; existing breadcrumb contracts |
| 11 Large-folder scrolling | Five virtual views, 2,000 PSD metadata entries, mobile width check, frame interval sampling |
| 12 Selection/multiselect | First click, modifiers, keyboard Home/End and offscreen focus; selection retained through pagination |
| 13 Search | Browser filtering, no new list calls, measured rendering; existing search scope retained |
| 14 JPG/PNG/WebP | Viewer handlers and mock small representations; Actual original request checked |
| 15 PSD | Best-effort mock preview, no original PSD transfer from viewer, unchanged native PSD contracts; no real PSD conversion claim |
| 16 Other supported types | Existing native Open/Open With, helper chooser and transfer contracts; helper compiled, no real application launched |
| 17–18 Zoom/pan/close | Browser controls exercised and Files selection retained on return |
| 19 Downloads | Real UI initiation, duplicate-click guard, existing authenticated redirects/transfer tests; no live file downloaded |
| 20 Upload/manage | Synthetic chunked upload completion, rename/delete/copy/move permission/API contracts and preservation checks; no live mutations |
| 21 Orders/Edition Ops exact file | Unchanged overlay installer, exact ID/revision checks, selection before paging, denied/missing/similar-ID fixtures, Orders state preserved |
| 22 Reopen | Warm folder/history/launcher and same-viewer image reuse; backend derivative cache tests; real cross-process cache behaviour unmeasured |

Commands and final implementation results:

- `.venv\Scripts\python tests/run_files_performance.py`: **145 passed**. External sockets denied, provider environment stripped. Includes cache races/invalidation/isolation, staff permission checks, API regression and native preservation/compilation tests.
- `node tests/test_files_performance_v2.cjs`: **passed**, paired baseline/current Chrome benchmarks and end-to-end synthetic scenarios.
- `node tests/test_files_premium_ui.cjs`: **4 scenarios passed**.
- `node tests/test_psd_modal_files_ui.cjs`: **9 scenarios passed**.
- `node tests/test_files_native_v2_ui.cjs`: **9 scenarios passed**.
- `python scripts/validate_render_topology.py`: **passed**; no topology changes.

The initial baseline Python run exposed five obsolete static assertions; those were aligned with existing native behaviour and intentional V2 contracts. They are not counted as newly fixed product bugs. Preservation tests compare unchanged native operations, Auto Editions API, Dropbox integration and Supabase backend with the fixed baseline rather than moving HEAD.

Runtime: local Python 3.13 virtual environment, Node 24 and bundled Playwright/Chrome. Installed test dependencies include Pillow 12.3, Starlette 1.8 and Streamlit 1.65; this is not an exact production-runtime reproduction. Use the pinned deployment environment for later integration acceptance. Screenshots: [desktop](files-performance-v2-evidence/files-grid-desktop.png), [mobile](files-performance-v2-evidence/files-grid-mobile.png), [preview](files-performance-v2-evidence/files-preview.png).

## Integration status and remaining work

Only four application files change: the existing Files window, image viewer, launcher and `files_upload_api.py`. Supporting tests and this report are added/updated. Auto Editions V11 code, mappings, allocations, generator, master preparation, production services and other worktrees were untouched. Existing API defaults, auth and staff permission checks are preserved; the new endpoint and preview parameters are additive. There is no second Files system.

All executed synthetic regressions pass. This is evidence of the covered behaviour, not confirmation that every live integration is working. After V11 finishes, review/rebase against the legitimate live revision and run authorised non-production tests with real Dropbox, pinned server dependencies and desktop helpers. Measure provider/auth/backend timings and real cold large-artwork preview availability. A separately approved derivative-generation/storage workflow would be needed to guarantee fast cold previews for formats/sizes Dropbox will not convert; this change deliberately does not alter V11 or invent that workflow.

The isolated implementation is suitable for later safe integration **review**, with real-provider acceptance outstanding. Do not deploy this branch directly over V11. The commit containing this report is the reviewable implementation revision; retrieve it with `git log -1` in this worktree.
