# Files V2 — web-only Open and embedded previews

14 October 2026. Worktree: `C:\Dev\SportsCaveWorktrees\sports-cave-files-performance-v1`.
Branch: `codex/files-performance-v1`; Studio task `20261014-50508219`, owner `codex/files-performance-01a1391d`.
Comparison baseline: `7ad3606536dd5e595b028443aa271f0f2e461082` (the first V2 commit). This report supersedes the earlier report's native-opening behaviour; the earlier V2 performance work remains in the branch.

## Result and removal boundary

**Open now means preview inside the existing Files interface.** Double-click, toolbar Open, context-menu Open and Enter use one embedded viewer. Folders navigate normally. Unsupported formats show a compact message with Download available. Image previews reuse the existing bounded caches and request screen representations; full-resolution raster inspection remains explicit. No Files helper handshake, version check, sign-in prompt, protocol launch, localhost request or preview popup remains.

Removed Files-only components and consumers:

- `files_native_launch.py` and `components/files_window/native_launch.html`, including launch creation/claim/cancellation and the secondary desktop sign-in handoff.
- `/files-native-launch`, `/api/files-native-open`, `/api/files-native-launch`, `/api/files-native-launch/claim`, and the Files grant-creation endpoint `/api/files-native-transfer`.
- Files and image-viewer WebView bridge listeners/hello messages, native capability/version state, desktop clipboard/outbound drag, helper installation/update controls, Open With, default-application preferences and desktop/folder launch actions.
- The older `files_chunk_uploader` component's protocol launch and File Explorer action. Its existing open event now requests the in-app preview. Its explicit download uses a hidden frame rather than a new window.
- Legacy Files application-choice helpers, helper notice styles and original-image preview links. The legacy Streamlit route reuses the same authenticated viewer for image/PDF/unsupported previews and retains its existing Back/breadcrumb controls and audio/video playback.
- Tests exclusively for the retired launch/claim module and page, replaced with web-only behaviour and removal/preservation assertions. No package dependency was exclusive to the deleted Python module; it used standard-library/otherwise-shared imports.

**Verified shared dependencies were retained:** repository references show Auto Editions setup, edition tests and PSD opening depend on `NativeTransferManager.create_psd`, transfer manifest/content endpoints, PSD routes and the companion package. These shared implementations remain unchanged. `/api/files-native-transfer/manifest`, `/api/files-native-transfer/content` and `/api/files-desktop-helper` intentionally remain for those other systems. Shared Windows/Mac companion sources can retain dormant capabilities; Files no longer invokes them and its launch/grant-creation routes are removed. Installers, authenticated Windows companion, Developer Studio, Design Studio, Photoshop preparation host, V11 generator/mappings/allocations and Render configuration were not modified.

## Performance implementation

- Create the preview frame only on the first Open, then reuse it. Load the selected path in the initial viewer URL, avoiding an extra startup message round trip. The existing same-origin/source-checked message channel handles subsequent opens, navigation metadata, closing and downloads.
- Show the preview shell immediately. Keep Files selection, scroll, search and navigation state behind it; restore focus on close. Abort obsolete preview work and stop PDF rendering/workers on close. Retain bounded 30-second image blobs and at most one PDF blob up to 8 MiB for warm reuse.
- Preserve V2 virtualisation, progressive pages, request deduplication, folder cache invalidation, visible-first thumbnails and direct saved-ID lookup. Remove unused native drag click suppression; reset duplicate-open state during folder navigation so immediate re-entry is reliable.
- Keep image previews small, with cached thumbnail handoff and explicit Actual/Download for originals. Never automatically fetch a layered PSD or full JPG for a thumbnail.
- Add authenticated, root-scoped PDF preview with metadata/revision checks before streaming. Reject PDFs above 25 MiB before their content transfer. No arbitrary URL proxying.
- Render PDF pages with pinned Mozilla `pdfjs-dist` 6.4.299, loaded lazily from local versioned assets. Parsing uses its worker; render one page at a time, cap canvas size at five megapixels, support Previous/Next/Fit/zoom, cancel obsolete renders, and do not execute PDF JavaScript. No runtime CDN dependency. Renderer and worker total 507,484 bytes with the shipped gzip copies; fonts/maps/decoders load on demand. Assets are immutable code and can be publicly cached; artwork endpoints remain authenticated/private/no-store.
- Preserve saved Edition download routing when the embedded viewer asks Files to download the selected archived JPG.

## Measured before/after

Actual headless Chrome timings against the real checked-in HTML, with every network request intercepted using synthetic files. Folder delay is fixed at 30 ms, preview delay at 40 ms. Six samples per folder variant, four per preview variant. Values are **p50 / p95 milliseconds**; with these sample counts p95 is the maximum, not a production service percentile. The current workstation's background load was not controlled and V11 was never interrupted.

| Action | Before | After |
|---|---:|---:|
| Cold 500-entry folder | 95 / 194 | 94 / 96 |
| Cold 2,000-entry folder | 108 / 117 | 102 / 104 |
| Cached 2,000-entry folder | 6.4 / 6.8 | 6.4 / 6.5 |
| Uncached 2,000-entry navigation | 58.2 / 70.3 | 57.5 / 59.2 |
| Back, 2,000 entries | 5.3 / 5.5 | 5.2 / 5.3 |
| Forward, 2,000 entries | 5 / 5.2 | 4.9 / 4.9 |
| Search, 2,000 entries | 1.5 / 2.1 | 1.4 / 2.2 |
| Selection, 2,000 entries | 0.3 / 0.4 | 0.3 / 0.4 |
| Cold file double-click to usable preview | 108 / 111 | 77 / 77 |
| Close and reopen same preview | 74 / 83 | 30 / 30 |
| Standalone image first usable | 90 / 90 | 86 / 88 |
| Redisplay already-open cached image | 0.8 / 1 | 0.9 / 1 |

Raw final samples: [metrics](files-web-only-v2-evidence/metrics.json). Also retained: [interim variable run](files-web-only-v2-evidence/interim-variable-run.json) and [before startup refinement](files-web-only-v2-evidence/before-startup-refinement.json). The latter exposed extra cold-start handoff cost; the final initial-URL change removes that wait. Small folder/search differences vary between runs and should not be attributed to helper removal. The main gains are removal of native preparation/handshakes and reusable embedded preview reopening. No blanket claim that every individual latency improved is made.

The unchanged launcher control measured 114 → 95 ms in one sample; both use the current Files shell, so this difference is **not** evidence of a new launcher optimisation. Warm launcher reopen made zero listing calls in both versions. The 2,000-entry shell measured 26.3 / 34.7 → 24.9 / 26.3 ms. Existing virtualisation retains 56 rendered rows; DOM elements changed from 568 to 559. CDP heap at the checkpoint was 3,788,024 → 3,777,552 bytes; cumulative script duration 12.71 → 12.14 ms. These are local browser measurements, not server memory/CPU.

Scroll frame intervals were 16.7 / 16.9 ms. Two viewports out of 1,000 files requested 60 thumbnails; maximum live browser requests remained four. Mock responses can finish after cancellation, so provider-side concurrency may be higher. Exact archived JPG selection took 113 ms in the synthetic Orders overlay, before pagination and without downloading image contents. Closing Files preserved the Orders filter.

The standalone image request totals include an extra explicit Actual action only in the after variant; they are not comparable preview-only request counts. Embedded close/reopen is asserted to reuse the image representation without a new preview request. PDF renderer assets are asserted absent before a PDF is opened, and a warm PDF reuses its cached bytes.

## Acceptance and preservation

Passed on the final implementation:

- **138 Python tests** via `tests/run_files_performance.py`: external sockets denied and provider environment stripped; Files operations, authentication/permissions, cache races and invalidation, PDF scope/revision/size/stream cleanup, safe static assets, helper removal, and shared-source preservation. The existing Windows helper still compiles; no application is launched.
- **11 additional isolated Python tests** covering the legacy Files open contract and synthetic shared PSD metadata/grant/permission protections.
- **Four complete browser journeys** via `tests/test_files_premium_ui.cjs`, simulating Windows, Mac, mobile and a WebView with a live bridge trap. All Open entry points, JPG/PNG/WebP, best-effort PSD representation, two-page PDF with nonblank canvas verification, zoom, close/reopen, cancellation, denied preview, unsupported Download, folder traversal, selection/search, folder creation, rename/delete and internal copy/move pass. Assertions require zero helper messages/requests, protocol launches and new windows.
- `tests/test_files_performance_v2.cjs`: paired benchmark plus 2,000-file/five-view virtualisation, thumbnail concurrency, progressive pagination, search, history/scroll/selection restoration, rapid navigation, upload chunks, download initiation and exact saved Edition navigation.
- **Nine PSD modal/Files scenarios** pass, including unchanged non-Files Photoshop opening through the shared host and exact linked PSD selection without invoking that host from Files.
- `tests/test_auto_editions_setup_ui.cjs` passes its synthetic candidate dimensions, explicit quality approval and stale-layout fence checks.
- Render topology validation passes. No deployment or Blueprint sync was attempted.

Studio's whole-file scan flagged an unchanged literal in the pre-existing credential-audit test. It was replaced with an explicit generated synthetic marker and that audit test passed; no credential value was exposed or used.

Source guards compare shared companion, Design Studio, Developer Studio, Auto Editions, Dropbox/Supabase modules and transfer consumers with `7ad36065`. An AST comparison limits `app.py` changes to Files functions and the Files helper CSS container; unrelated application functions remain identical. Shared grant manager, manifest/content and package handlers are compared byte-for-byte.

Broader full-Streamlit AppTest execution was not completed: this isolated environment lacks `python-dotenv`; an optional edition-test suite also needs `pytest`, and a separate PSD audit fixture CSV is absent. Those attempts were not counted as passes. No production fixture was sought as a substitute. Changed legacy preview functions were additionally executed in an AST-extracted synthetic harness without loading application credentials. Local Python 3.13 and current test packages still differ from the pinned production runtime.

Visual evidence: [embedded image](files-web-only-v2-evidence/files-preview.png), [PDF desktop](files-web-only-v2-evidence/files-web-pdf-Win32.png), [PDF mobile](files-web-only-v2-evidence/files-web-pdf-iPhone.png). The initial native PDF embed failed visual verification and was replaced; the final tests check actual rendered page pixels and page navigation, not merely an iframe/object URL.

## Remaining limitations and integration readiness

No authorised non-production Dropbox environment was available, so provider latency, live large artwork and real staff sessions were not benchmarked. Dropbox documents thumbnail limits (supported raster formats, at most 20 MB; PSD is not listed). The existing best-effort PSD/lightweight preview path therefore cannot guarantee a fast cold preview for every large PSD or 35 MB JPG. The viewer never silently downloads the original to mask this; it shows the failure/fallback, with explicit Actual for raster inspection and Download for unsupported files. Original artwork and resolution are unchanged. See the [official thumbnail documentation](https://dropbox-sdk-python.readthedocs.io/en/latest/api/dropbox.html#dropbox.dropbox_client.Dropbox.files_get_thumbnail).

PDF preview currently receives the complete bounded PDF before rendering, not range-based page streaming. Encrypted/malformed/oversized PDFs may require Download. PDF text selection/forms/annotations are outside this basic visual preview; unsupported content fails visibly. No new file-storage service was introduced. PDF.js is a pinned vendored dependency with licences and an archive checksum in its `SOURCE.json`; future security updates must update the versioned asset route too.

The isolated implementation is ready for review and later safe integration testing. It is **not deployed and not certified against live Dropbox**. After V11 finishes, compare/rebase onto the latest legitimate main revision, test with the pinned runtime and authorised provider access, then release separately with the user's deployment authorisation. Do not deploy this branch over the active V11 work. Retrieve the local commit containing this report with `git log -1` in the named worktree.
