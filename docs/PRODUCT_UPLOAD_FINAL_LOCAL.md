# Product Uploads — consolidated local upload optimisation

## Gallery and clipboard correction — 19 October 2026, local only

Release follow-up: the user subsequently explicitly authorised pushing this
gallery/copy correction to Git/Render and verifying the deployed version. The
local-only statements in this section describe implementation-stage status.
Release evidence is retained under ignored
`output/product-upload-gallery-regression/`; existing speed/progress, Save all
and standalone Mockups implementation files are unchanged by this release.

Worktree: `C:\Dev\SportsCaveWorktrees\sports-cave-products-product-uploads-integrated-existing-mockup-20261018-4b18037e`.
Branch: `codex/task/products-product-uploads-integrated-existing-mockup-20261018-4b18037e`,
base `eb74083066591d0dd5ff652059afdb1615614ae3`. No commit, push or deployment for this correction.

The completed-results renderer replaced the small generation strip with five
315px component cards and mounted a separate inline master-prompt editor.
It now keeps one ordered, compact preview row and exactly two clipboard buttons
above the unchanged lifestyle upload cards. A keyed Streamlit component handshake
replaces the unkeyed inline-script iframe controls. The prior missing-button
symptom was not reproduced against an authenticated production browser; no CSP
cause is asserted. Inline editing is removed from Product Upload.

Previews reuse `image_factory.create_preview_file`: WEBP, maximum edge 900px,
quality 70, method 4, preserving aspect ratio. Preview payloads are cached by path,
size and modification stamp (80-entry bound). Original URLs carry metadata only;
no original bytes enter component arguments. Original retrieval is restricted to
explicit preview links and Copy black frame. The existing authenticated original
registry, source checks, export manifest, encoder and save services are retained.

Focused checks: 11 tests passed in `tests/test_product_upload_gallery.py` and
`tests/test_product_upload_outputs.py`; Node syntax check passed for the new
component script. `scripts/verify_product_upload_gallery.py` passed using installed
desktop Chrome in headless mode against the loopback outputs fixture, reading
the affected PSD without changing it. Network assertions confirm zero original
requests on initial rendering and a full rerender, one correct original per
explicit preview open, and no browser original retrieval during Save all.
During generation, existing lightweight progress previews remain one row; after
completion they are replaced by the single permanent five-preview row.

Measured preview files for this fixture, all 900×900 WEBP: Black 75,288 bytes;
Oak 88,846; White 75,140; Unframed 84,198; Size Guide 55,798. They display within
140×110 boxes with intact aspect ratios. Black-frame clipboard PNG dimensions
and pixels match the 1000×1000 generated original. Full master text, clipboard
denial errors, keyboard opening, all five original links, all three uploaded
2000×1200 lifestyle originals, mocked Save all (16 original-derived WEBP/JPG
outputs), and stale-link revocation passed. Browser JavaScript errors: none.
Existing focused export tests cover original encoder parity, partial retry,
duplicate submission, collisions and revision fences.

Evidence: ignored `output/product-upload-gallery-regression/` contains
`tests.log`, `ui-results.json`, `browser.log` and screenshots. No external ChatGPT
generation, OS paste target, authenticated production browser, Dropbox export
writes or live Shopify operations were tested. Companion calls are prohibited in
the fixture. Standalone Mockups, merged prompt content, speed/progress code and
Save all services have no changes in this correction; no performance benchmarks
were restarted. The older release notes below describe previous work only.

Release authorisation — 19 October 2026: the user subsequently authorised
publishing both the speed/progress work and lifestyle/copy/Save all changes to
Git/Render, and updating the installed Companion. The local-only sections below
describe implementation-stage status. Combined pre-release verification passed
56 focused tests plus the optional affected-PSD test run separately (57 total),
Node picker/state checks, Render topology validation and Studio verification.
Exact release/deploy/Companion evidence is recorded under ignored
`output/product-upload-combined-release-20261019/`; no live artwork/Shopify test
writes are part of release verification.

Companion release verification found one retained workflow-v2 manual-upload render
request repeatedly receiving scope-denied HTTP 403. Its staged source is under
`product_upload_assets`, outside the current approved design folders. The native
claim endpoint now checkpoints only that unsupported request as failed with an
actionable Dropbox-selection reason, retaining its staged file and source metadata.
It returns no native grant and lets subsequent host polls continue. This does not
relax the approved-folder rules, touch originals, or change workflow-v3 server
preparation. Focused tests cover source retention, absence of a native grant,
non-retryable scope failure, a healthy subsequent poll and valid host claims.

## Master lifestyle brief, originals and Save all — 19 October 2026 (local only)

Verified existing worktree:
`C:\Dev\SportsCaveWorktrees\sports-cave-products-product-uploads-integrated-existing-mockup-20261018-4b18037e`
on `codex/task/products-product-uploads-integrated-existing-mockup-20261018-4b18037e`,
task `20261018-4b18037e`, owner `codex-products-mockups-20261018`.
HEAD remains `e4efe300aeeb9ba59e8277f637b0d162d8da01cd`. Existing unfinished
speed/progress changes were snapshotted under ignored
`output/product-upload-lifestyle/before/` before editing overlapping files.

Files for this continuation: `product_upload_lifestyle.py`,
`product_upload_outputs_ui.py`, `product_upload_gallery.py`,
`components/product_upload_gallery/index.html`, `product_upload_export.py`,
`product_upload_mockups.py`, `product_upload_mockups_ui.py`,
`product_upload_api.py`, `components/product_uploads/index.html`, this report,
`tests/test_product_upload_outputs.py`,
`tests/fixtures/product_upload_outputs_provider.py`,
`tests/fixtures/product_upload_mockups.py`,
`scripts/product_upload_outputs_preview.py`, and
`scripts/verify_product_upload_outputs.py`.

Product Upload now has its own presentation around the existing engine. It
reads the three saved lifestyle overrides, including legacy keys, and uses the
existing prompt store/editor with a separate `lifestyle::product-upload-master-v1`
key. Shared templates and standalone Mockups are unchanged. Default room/angle
draws are deterministic for the workflow; authored selections remain intact.
One master brief repeats exact-product/A1/glazing requirements in each of three
labelled scenes and requests separate, sequential, approval-gated ChatGPT images.
The OS does not control that external conversation. Existing XL 62 × 87 cm is
a nominal display reference, not evidence of exact outer-frame measurements.
The master distinguishes A1 paper (841 × 594 mm, reversed for portrait) from
unknown outer-frame/mount/depth dimensions and flags conflicts rather than
inventing allowances or deforming the reference. Material claims remain unchanged.

The compact copy row precedes the same Man Cave, Office and Living Room cards.
Every preview opens its own original on click/keyboard. Original delivery is
on demand, authenticated and bound to workflow/source/asset; replaced assets,
other actors and revoked selections cannot use an old link. Image copying
reports success only after Clipboard API completion. PNG conversion retains
dimensions. Uploaded lifestyle originals are retained separately from the
shared size-limited export assets; they are not substituted into production
exports. Clipboard denial offers Open original and never substitutes text/URLs.

Confirmed previous mismatch: Product Upload delegated to the standalone result
renderer, exposing group/ZIP controls and eagerly building ZIPs. Its export
wrapper forced merge/replace for a reserved target. Product Upload now renders
Save all only, without ZIP assembly, and uses the same ordered asset manifest,
namespace/path helpers, folder service and upload_batch service as Mockups.
The picker starts from the configured Files team root plus
`04_OUTPUT/product-images`; only a direct child sport collection is accepted.
The current Product name supplies the sanitised output folder automatically.
Existing folders get a numbered destination; atomic creation and provider ID
checks prevent merging into another product's folder. The existing intake save
ledger now checkpoints folder ownership and confirmed files. Hash/size checks
recover partial/lost acknowledgements without overwriting or re-uploading
confirmed bytes. Transfers use the existing application job runner with real
byte/file progress, duplicate fencing and no Companion calls. Saving does not
run PSD preparation/generation or change Shopify collections/publication/PSDs.

Settings reused, without a new encoder: generated outputs retain aspect ratio
with the shared maximum 1600-pixel edge; WEBP quality 82/method 4; JPEG quality
92/optimise. Product lifestyle imports retain aspect ratio, use the shared
1600-pixel export bound and lossless WEBP/method 1. Preview encoding is separate.
The existing manifest selects ordered `WEBP/` and `jpg/` files (16 for all eight
ready product images). The social JPG preparation remains internal. Existing
upload/pixel/memory limits and colour handling are unchanged; no new target KB
limit or invented crop/size/quality setting was introduced.

Focused verification: eight new regression tests plus existing export-binding
and durable-save regressions passed (10 distinct tests). An actual encoder fixture
compared the standalone save implementation's original paths, names, order,
dimensions and hashes against Product Upload's confirmed uploads. Tests covered
partial retry, lost acknowledgement, duplicate completion, numbered collisions,
conflicting destination bytes, source/revision/actor fencing, stable custom
scenes, original retention and absence of ZIP controls.

Installed Chrome (headless) exercised the actual local Product Upload with the
affected Jake Bauers PSD read-only, synthetic lifestyle uploads, isolated SQL,
mocked Dropbox writes and Companion calls prohibited. It verified all eight
originals open, keyboard opening, a 1000 × 1000 black-frame clipboard PNG with
identical decoded pixels, retained/copied 2000 × 1200 lifestyle originals,
honest clipboard denial, correct picker root, visible saving progress and
interactive form. A forced file failure retried into the same folder: 17 upload
attempts for 16 confirmed files, one folder reservation. Old image links were
revoked on source removal and a fresh page stayed empty. No browser JS errors.
Evidence: `output/product-upload-lifestyle/{ui-results.json,tests.log,ui.png}`;
test tools: `scripts/product_upload_outputs_preview.py` and
`scripts/verify_product_upload_outputs.py`. No PSD benchmarks were restarted.

Limitations: no production Dropbox test exports, external ChatGPT generation,
visual A1 accuracy, operating-system paste or live saved-prompt persistence were
verified. Writes were mocked; shared prompt persistence uses the existing
Developer mechanism. No commit/push/merge/deploy, live Shopify changes, source
PSD rename/move/modification or Companion update was performed.

How To: choose a PSD and Generate mockups; paste Copy black frame into ChatGPT,
then Copy prompt. Approve each separate scene before the next and upload it to
its matching card. Click previews to open originals. Save all → sport collection
→ Save here creates the Product-name output folder. Retry that same destination
after a partial failure; confirmed files are verified and skipped. The page's
existing How to panel has the same updated instructions.

## Responsive preparation and generation — 19 October 2026 (local only)

Continued in the existing PRODUCTS worktree and branch, starting clean at
`e4efe300aeeb9ba59e8277f637b0d162d8da01cd`. The working Dropbox revision-path
download remains unchanged. No commit, push, deployment, live Shopify mutation,
original PSD change or Companion update is authorised or performed here.

Confirmed blocking paths: the preparation HTTP request waited for download,
hashing and decoding; its database transaction/advisory lock spanned that whole
operation and blocked progress reads in the isolated database transport. Generate
ran the image engine on the Streamlit render thread. Prompt/export/ZIP assembly
also ran on the UI thread. State reads, metadata checks and five-second fragment
polling added latency. Neither the normal cold/cache sequence nor Generate
duplicated the PSD download: the before and after browser runs each transferred
the original once across two selections and two generations.

Both operations now use bounded application thread jobs, following the existing
PostingJobs/Files-preview executor pattern. The unchanged shared Mockups engine
provides actual completed-asset callbacks. Workers never read or mutate Streamlit
session state. Preparation uses a short source-specific database claim with a
five-minute renewable lease, commits before downloading and decoding, and fences
completion by source/attempt. UI polling reads lightweight job snapshots; normal
progress never rebuilds the entire page. Terminal updates rerun once, including
failures. Duplicate submissions share a running job; old tokens and selections
cannot publish their results. Process loss remains retryable from the exact source.

The selected PSD shows actual download bytes/total and percentage, followed by
Checking file, Preparing artwork and Ready. Unmeasurable stages use indeterminate
bars. **Generate mockups** is disabled until artwork is ready and while rendering.
It acknowledges immediately, shows actual completed-image counts and lightweight
completed previews, then enables the unchanged lifestyle/export/Shopify controls.
Prompt and ZIP finalisation reuse the existing functions in the worker. Colour
policies, full-composite decoding, resolution and generated image quality are
unchanged. Standalone `app.py`/`image_factory.py` and rename/move code are untouched.

Prepared source assets retain strict source/revision/settings/receipt hashes.
The disposable cache is limited to eight entries, 256 MiB and 24 hours; active
renderers pin their prepared asset. Processing settings or corrupt/missing assets
still invalidate reuse. Progress-preview bytes and retained jobs are also bounded.

Matched local Chromium runs used the actual Product Upload component, Streamlit
renderer and image engine, the affected 285,917,118-byte PSD read-only, disposable
PGlite and a provider stream limited to **32 MiB/s**. No credentials or external
requests were allowed. These are local UI measurements, not Render performance.

| Measurement | Before | After |
| --- | ---: | ---: |
| Cold selection to Ready | 11.125 s | 11.093 s |
| Cached selection to Ready | 0.281 s | 0.203 s |
| Generate to first feedback, cold | 0.125 s | 0.094 s |
| Generate to all five loaded images, cold | 5.219 s | 4.437 s |
| Generate to all five loaded images, cached | 5.156 s | 4.438 s |
| Metadata calls across both workflows | 39 | 34 |
| Original PSD downloads across both workflows | 1 | 1 |

This is a paired sample, not a statistically established production speedup.
Cold time did not materially improve: the controlled stream occupied about
9.1 seconds, checking about 0.19 seconds and artwork/preview preparation about
1.31 seconds. Cache-hit processing took 78 ms plus UI delivery. The major change
is responsiveness throughout work. A separate UI recovery run received a server
interaction in 78 ms during rendering, retained form values, retried the same
workflow after an injected provider failure, disabled repeated generation, changed
selection mid-render without stale images, and opened a fresh page with no image.
All five final previews were loaded and visually inspected as the Jake Bauers design.

Focused evidence, stage timestamps, screenshots and source-hash checks are under
ignored `output/product-upload-responsive/`. The earlier authenticated Render
download of 6.42 seconds remains a separate measurement. Live UI latency, Render
CPU contention and its network/database queue times have not been benchmarked;
the available log query did not supply a matching flow for this continuation.

How To: choose the Dropbox PSD, watch download/preparation progress, then select
**Generate mockups**. Product details remain editable while work runs. Retry
retains the source and form; reselect when its revision changes. Wait for all five
mockups before continuing with the existing lifestyle images, exports and Shopify
actions. Companion remains solely the separate post-Shopify rename/move trigger.

Implementation files: `product_upload_jobs.py`, `product_upload_artwork.py`,
`product_upload_services.py`, `product_upload_api.py`, `product_upload_dropbox.py`,
`product_upload_intake.py`, `product_upload_mockups_ui.py`, the existing component
JS/HTML and this report. Focused tests and loopback-only benchmark/verification
fixtures are included; their external boundaries are explicitly isolated.

Verification: 48 distinct focused Python tests passed across the 47-test
regression and six job/callback follow-up checks (one newly added test), plus
the Node component-state test and changed-file syntax checks. Actual Chromium
recovery/progress checks passed against the affected read-only original with
Companion calls prohibited. No unrelated suite was repeated.

Test files: `tests/test_product_upload_jobs.py`,
`tests/test_product_upload_server_artwork.py`,
`tests/test_product_upload_artwork_recovery.py`,
`tests/test_product_upload_original_download.py`,
`tests/test_product_upload_browser_transport.py` and
`tests/test_product_upload_state.cjs`. Harness files:
`scripts/product_upload_responsive_preview.py`,
`scripts/benchmark_product_upload_responsive.py`,
`scripts/verify_product_upload_responsive.py` and
`tests/fixtures/product_upload_responsive.py`.

## Original download HTTP 400 — 19 October 2026 (local, deployment held)

Release follow-up: the owner subsequently authorised committing and pushing this
verified fix to GitHub/main and deploying the existing Render services. The
local-only/deployment-held statements below describe the implementation stage.
Exact release SHA, deploy IDs and health results are recorded separately under
`output/product-upload-original-retrieval/` and in the Studio task registry.

The owner reproduced the original request inside canonical Render service
`sports-cave-os` with its existing credentials and Dropbox SDK 12.2.3. Dropbox
returned HTTP 400, request ID `d5ef2597c30f4b15bbc596086ad5571d`, explicitly
rejecting the deprecated separate `Rev` parameter and requiring `rev:{rev}` in
the path. This confirms the retrieval failure; it is not evidence of a damaged
PSD or missing permission. Historical reference `63f6f9f94221` records the same
operation and `BadInputError` for the selected file ID and revision.

Product Upload now reuses Files' corrected original-PSD streaming helper. It
requests `rev:<selected revision>` through the existing rooted client, verifies
the returned stable file ID and revision before streaming, and compares size and
content hash metadata. Timeout and provider retry counts are bounded. Streaming
checks the byte count and PSD signature, closes the response and deletes partial
temporary outputs on failure. Preparation still verifies the complete Dropbox
content hash before the unchanged full-composite/ICC decoder and shared Mockups
engine. The companion and browser do not transfer or prepare the PSD.

How To: keep the selected PSD and product form, then use **Retry artwork
preparation** after this correction is installed. Wait for **Ready** before
**Generate Core Shopify Images**. If identity changed, refresh the Dropbox picker
and reselect the current revision. The close icon, Escape, focus return, Review/
Live selector and breadcrumbs remain unchanged.

Local verification and its network boundary are recorded under ignored
`output/product-upload-original-retrieval/`. SDK/HTTP regression tests isolate
upstream transport; the affected original is read-only. The owner subsequently
ran the corrected revision-path request in the same Render Shell: HTTP 200,
request ID `c8e4da4f496940308d566ffc6ad558e0`, 285,917,118 bytes, verified PSD
signature and content hash
`c5c9b3192d5cb6a5c42a70ef465f02cae5fcc1d8a2a14fd7fa4b964ec74da72e`,
in 6.42 seconds. This verifies the complete original download with the actual
application credentials, SDK 12.2.3 and team-root context; no reconnection is
required for this request.

Separately, the corrected local adapter streamed the exact affected PSD through
full composite/ICC preparation and the unchanged shared core mockup engine,
with companion claims prohibited. All five core images were generated and the
preview and framed/unframed/size-guide outputs visually inspected. The final
local measured run prepared artwork in 1.80 seconds and generated core mockups
in 4.27 seconds, excluding real network transfer. These measurements are from
different runtimes and must not be added into a claimed Render end-to-end time.
Render's full UI preparation/generation has not run with the undeployed patch.

132 distinct focused tests plus eight subtests passed across the final regression
and follow-up checks; Node picker state, JavaScript syntax, Studio static checks
and diff whitespace checks passed. Two additional checks fail identically on
the unchanged baseline: a non-admin Photoshop-access expectation and a missing
local `approved_dropbox_psds_282.csv` snapshot. They remain unrelated and unchanged.

Changed files: `dropbox_integration.py`, `product_upload_services.py`,
`product_upload_artwork.py`, `tests/test_product_upload_original_download.py`,
`tests/test_product_upload_artwork_recovery.py`, `tests/test_psd_universal.py`
and this How To/report. `app.py`, `image_factory.py`, picker code, infrastructure
and companion code remain unchanged.

No commit, push, deployment, original artwork change or live Shopify write is
performed in this continuation. The owner explicitly placed deployment on hold.

## Preparation failure and picker follow-up — 19 October 2026 (local only)

Release follow-up: the user subsequently authorised committing/pushing both latest
updates, deploying the existing Render services and updating the installed Companion.
The local-only notes below describe implementation-stage verification. The original
production exception remains unrecoverable; deployment adds diagnostics without
claiming that the earlier 503 has been reproduced on Render. Release evidence is
recorded in `output/product-upload-picker-release-20261019/`.

Verified the existing task `20261018-4b18037e` and owner on its existing branch;
starting worktree was clean. No commit, push, deployment or installed worker change.

The affected Jake Bauers PSD is accessible read-only: Dropbox ID
`id:u1tYiAa2O-AAAAAAAABw6w`, revision `0165e251a26bf2f000000036d367e13`,
285,917,118 bytes, Dropbox content hash
`c5c9b3192d5cb6a5c42a70ef465f02cae5fcc1d8a2a14fd7fa4b964ec74da72e`.
A fresh server-side Dropbox download and the synced original both match this hash.
Document: 2835×2004, RGB8, embedded ICC 3144 bytes. Production Pillow 10.4
successfully decodes the full composite, preserves colour conversion and prepares
2000×1414 PNG artwork. The real shared Mockups engine produces all five core assets
from that exact artwork with actual repository scene templates and no Companion.
The standalone Mockups uploader accepts JPG/PNG/WebP in both this branch and the
current main snapshot; it has no separate PSD decoder to reuse. Neither it nor
`image_factory.py` was modified.

**The original production failure's precise operation remains unconfirmed.**
Runtime request logs show POST preparation 503 at 2026-10-18 22:47:35 UTC.
The old handler discarded the exception/stack and stored a generic composite error.
That evidence cannot be reconstructed from its saved text. Local baseline preparation
of the exact PSD also passed before these changes. No evidence justifies resaving
the PSD, changing colour policy, increasing memory/timeouts or adding a decoder.
The local correction therefore preserves decoding and retrieval, fixes error/retry
state and adds stage/type/stack/reference diagnostics without credentials, provider
response bodies or signed URLs. Future failures identify download, validation,
decode, preview, storage or checkpoint stages rather than blaming the composite.
The generic HTTP error and stored preparation reason now agree.

Retries clear previous failure state, reuse verified assets, join an already running
request and fence completion/failure by source and attempt. Generate Core Shopify
Images is disabled until artwork is Ready; selected and failed artwork has a separate
Prepare/Retry control. Late generation results are discarded after a new selection.
The picker close icon is at top-right, labelled Close Dropbox picker. Close and Escape
cancel only metadata browsing, preserve the selected PSD/form and return focus to
Choose PSD. Review/Live remain; breadcrumbs replace Up. How To is updated briefly.

Evidence: ignored `output/product-upload-preparation-fix/` contains baseline decode,
complete retrieval verification, real-PSD timings and focused verification. Timings
use a disposable database/provider metadata and a byte copy from the verified
retrieval; they do not reproduce Render resources or prove the production 503 is
resolved. Original Dropbox files and live Shopify products remain untouched.

Verification: 160 distinct tests plus 49 subtests passed (159-test regression,
then 21 focused tests after final error-bootstrap changes, including one new test).
Node state/syntax, Studio Verify, topology and diff checks passed. Actual Chromium
checks cover pending metadata close, Escape/focus, breadcrumbs, retained form,
selection changes, desktop/mobile and iframe fit. Decoder AST, standalone Mockups,
shared engine and infrastructure files are unchanged.

Changed files: `product_upload_artwork.py`, `product_upload_api.py`,
`product_upload_mockups_ui.py`, `components/product_uploads/app.js`,
`components/product_uploads/index.html`, `tests/test_product_upload_artwork_recovery.py`,
`tests/test_product_upload_server_artwork.py`, `tests/test_product_upload_browser_transport.py`,
`tests/test_product_upload_state.cjs` and this existing How To/report.

## Release authorised — 19 October 2026

The user authorised publishing both Dropbox selection and server-side PSD
preparation updates to Git/Render and updating the installed Companion.
The local-only statements below record the implementation-stage boundary.
Release verification includes production Pillow 10.4 compatibility, unchanged
standalone Mockups, canonical Render topology and preserving current recovery
fixes from main. Deployment and installed-release evidence is recorded separately
in the task output and Studio registry. No original artwork or live Shopify
product is used as a release test.

## Dropbox PSD correction — 19 October 2026 (local only)

Choose PSD opens the in-app Dropbox picker. Review defaults to the verified
`99_PSD_NEEDS_REVIEW_DO_NOT_DELETE` folder inside
`/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED`.
The real folder remains unchanged. Files metadata is paginated; PSD bytes never
travel through the browser. Product details, prompts, lifestyle controls, exports
and Shopify actions retain their existing workflow.

Tracing this worktree found that `app.render_mockups_page` accepts JPG/PNG/WebP
and calls `image_factory.generate_product_images`, whose working-artwork loader
also accepts those formats. It did not contain an independent PSD implementation.
Both `app.py` and `image_factory.py` remain unchanged. Product Upload therefore
uses a small server PSD adapter before that exact shared generation engine.

Selection binds immutable Dropbox ID, revision, hash and current path. The browser
then requests server preparation using JSON only. The app server downloads the
pinned original to disposable staging, verifies size/content hash, reads the
full-resolution saved PSD composite through Pillow, preserves approved ICC
handling through LittleCMS, and creates a lossless sRGB PNG up to the shared
2000px working limit. The unchanged engine creates the core product images,
lifestyle references, prompts and export assets. Generate Core Shopify Images
remains explicit. No thumbnail is used for production artwork.

Preparation uses the same image-dimension and memory admission checks as Mockups.
RGB8 PSD raw/RLE saved composites are supported. Unsupported encoding, missing or
truncated composites, unsupported colour modes/depth, unapproved untagged sources,
changed revisions and insufficient resources fail clearly. The decoder reads the
saved merged composite; it does not recomposite arbitrary live layer effects.
Existing reviewed colour-recovery policies remain required and unchanged.

Disposable prepared PNG/preview assets are reused only after source, processing
settings, Pillow/code/colour-policy fingerprints and output checksums match.
Expired or corrupt caches rebuild from the pinned source. One server preparation
runs at a time per process, with source-specific DB deduplication. Fresh pages
remain empty and stale selection responses cannot replace the current design.

**Companion is not used for selection, preview, PSD preparation or generation.**
It remains only the trigger for the separate durable post-Shopify rename/move
handoff. Offline handoff stays queued and does not block mockups or Shopify
confirmation. Drafts remain in Review; publication/media gates and conflict,
revision, pause and processing protections still apply to file operations.

Focused verification uses disposable PostgreSQL, actual synthetic PSD bytes,
real Pillow/ICC conversion, real shared generation with isolated scene templates,
and Chromium desktop/mobile/embedded-frame UI. No Companion is connected or
invoked. Exact prepared-preview pixels, cache reuse/invalidation, truncated
composites, approved colour recovery, stale sources and generation-button wiring
are checked. Measurements and the full verification/file list are under
`output/product-upload-server-correction/`; browser measurements are under
`output/product-upload-dropbox/`. These are local synthetic measurements, not
production Dropbox bandwidth or large-design timing. Main bottlenecks remain
source transfer, full-resolution decode and existing server memory/pixel limits.

No commit, push, deployment, installed Companion change, live Shopify mutation
or original Dropbox file modification was performed. Previous uncommitted work
is retained, with a before-correction snapshot in the ignored output directory.

The binary-transfer results below are historical; that transport is no longer
Product Upload's PSD source-selection path.

Status: Implemented locally. Not committed, pushed, merged or deployed.
Task `20261018-4b18037e`, owner `codex-products-mockups-20261018`, existing branch
`codex/task/products-product-uploads-integrated-existing-mockup-20261018-4b18037e`.

## Completed result

The existing 8 MiB binary request now streams through an ordered writer in 4 MiB
checkpoint frames. Reception of the second frame overlaps storage of the first.
The final controlled Chromium comparison transfers the same 188.65 MiB PSD in
**61.22 → 53.52 seconds (12.6% less time)**. Selection-to-Uploaded falls from
**62.74 → 55.11 seconds**; effective transfer throughput rises from
**3.081 → 3.525 MiB/s**. HTTP chunk count stays at 24.

These are actual Chromium-to-local-HTTP measurements with simulated bandwidth,
latency and a disk storage double. **Real internet/Dropbox speed was not measured.**
No remote storage tests, production credentials/data, native jobs or production
writes were used. This concludes the authorised local implementation.

## Workspace preservation

Ran `git worktree list` from the main checkout and verified the requested root,
branch, registered task owner and existing changes. Read the Phase 1–2 reports
and retained all completed work. No additional relay implementation was present.
No new worktree or project folder was created. Saved the exact Phase 2 runtime
baseline in the existing ignored `output/product-upload-phase2` evidence folder:
`phase2-api.py`, `phase2-intake.py`, `phase2-app.js`. Historical reports and raw
results remain intact; no other task was edited.

## What changed and why

- **Bounded overlap inside the existing request:** one ordered provider writer,
  an AnyIO channel with one queued frame, and two frame permits. Active, queued
  and assembling frames together cannot exceed two 4 MiB buffers. The existing
  SDK needs at most one further 4 MiB immutable body copy. ASGI/network fragment
  and framework allocations are separate; no full PSD is buffered.
- **Admission across simultaneous uploads:** PostgreSQL transaction advisory
  locks allow at most two relay requests across processes sharing this database,
  and one request per intake. Admission happens before application body reads.
  Capacity exhaustion/uncertain prior writes return retryable 503 with Retry-After.
  At most two admission connections and two active checkpoint connections are
  needed concurrently. No durable queue, schema, service or infrastructure was added.
- **Authoritative progress:** each frame uses the existing row lock, validation,
  block digest, provider append and independent checkpoint transaction. An HTTP
  success waits for all its frames and the admission guard to settle. Queued or
  received bytes are never acknowledged as saved. The original per-block hashes,
  exact file identity and final independent storage hash remain authoritative.
- **Failure recovery:** cancellation stops further reception, discards uncommitted
  buffers and lets an active append/checkpoint settle. Restart resumes from SQL,
  without relying on a RAM queue. Replaying an 8 MiB legacy body revalidates the
  already confirmed prefix. An old 8 MiB provider append whose DB checkpoint was
  lost can be recovered as two verified 4 MiB checkpoints, with final storage-hash
  verification still required. Changed replay bytes are rejected.
- **Slow links:** binary requests now have a 60-second no-progress deadline,
  180-second post-send acknowledgement deadline and 15-minute absolute cap.
  Progress resets the idle deadline, so slow movement is distinct from a stall.
  Server reception has a 90-second idle deadline and 15-minute reception limit.
  Six attempts remain the maximum per operation; Interrupted retains the File.
- **Reconcile before replay/fallback:** the authenticated `resume` action obtains
  the same intake lease as the relay, returning only after prior writes settle.
  After an uncertain network/timeout error, the browser checks that authoritative
  offset before replay. A timeout selects supported 4 MiB requests only after
  reconciliation. Healthy connections keep 8 MiB. Older servers/clients retain
  compatible exact-body retry and 4 MiB fallback behaviour.
- **Connection safeguards:** actual database connections default to an eight-second
  idle-in-transaction limit. Upload-only guards use a transaction-local 20-minute
  limit; checkpoint provider-I/O transactions use a local five-minute limit.
  These reset on transaction completion and do not change DB-wide configuration.
  Append SDK clients clone the existing authenticated/rooted cached client while
  sharing its connection pool. Error/rate retries are limited to one each and
  socket timeout is 60 seconds; the SDK's formerly unlimited rate-retry default
  cannot retain relay capacity indefinitely through endless retries. Other cached
  clients/defaults remain unchanged. Provider-imposed waits are not real-world
  measurements or fixed wall-clock guarantees.

Hashing was left alone: it was already bounded and responsive. Original PSD bytes,
layers, quality, profiles, RGB8 checks, colour policy and 1 GiB limit are preserved.
No HTML/layout, manual workflow, integrated Mockups, separate Mockups page or
worker handoff was changed. Fresh pages still start empty without a stale preview;
explicit selection must validate the exact file before resuming. Upload alone
creates no worker jobs. Native processing is not included in transfer/finalisation.

## Small before/after comparison

Existing benchmark harness: `tests/benchmark_product_upload_browser.py`.
Same existing NON_PRODUCTION PSD: 197,816,894 bytes / 188.652891 MiB, content hash
`f1e90d6ef5f8f6083a0577c3846aec472050283c126a5a30cc8ccae4aa799c56`.
Actual headless Chromium, isolated loopback Uvicorn routes, disposable PGlite SQL,
synthetic account, disk provider. No full application server or native worker.

Controlled network profile is unchanged from Phase 2: 40 Mbps Chromium upload,
160 ms CDP latency, storage append delay 180 ms plus bytes at 100 Mbps. Browser
latency can overlap transmission. One new baseline and one final measurement per
profile; one initial relay measurement was retained before the final timeout/SDK
safeguards, then the final code was measured. No competing transfer system was built.

| Measurement | Phase 2 loopback | Final loopback | Phase 2 controlled profile | Final controlled profile |
|---|---:|---:|---:|---:|
| Selection to first send | 0.492 s | 0.386 s | 0.743 s | 0.834 s |
| Binary transfer incl. ACK | 1.622 s | 1.904 s | 61.222 s | 53.522 s |
| Finalisation | 0.185 s | 0.185 s | 0.757 s | 0.742 s |
| Selection to Uploaded | 2.311 s | 2.482 s | 62.739 s | 55.106 s |
| Effective transfer | 116.345 MiB/s | 99.108 MiB/s | 3.081 MiB/s | 3.525 MiB/s |
| HTTP chunks | 24 | 24 | 24 | 24 |
| Ordered provider appends/checkpoints | 24 | 48 | 24 | 48 |
| Peak sampled Python-process RSS | 89.75 MiB | 88.99 MiB | 90.99 MiB | 89.75 MiB |
| Python-process RSS growth | 9.25 MiB | 9.13 MiB | 9.70 MiB | 8.79 MiB |
| Peak sampled Chromium RSS sum | 313.37 MiB | 311.97 MiB | 321.95 MiB | 321.19 MiB |
| Main-thread tasks over 50 ms | 0 | 0 | 0 | 0 |

There is a **0.28-second loopback transfer regression** from additional framing,
checkpoints and admission/SQL safeguards when there is no storage/network delay to
hide. The intended latency profile saves 7.70 seconds; the change is retained for
that useful result rather than claiming every connection gets faster. Final hash
checks remain unchanged; no optimisation claim is made for startup/finalisation.

Controlled-stage totals explain the gain: browser reception remains approximately
40.3 → 40.2 seconds (ideal payload time at 40 Mbps is 39.56 seconds). Aggregate
provider time increases 20.30 → 24.73 seconds due to smaller appends, but now overlaps
reception; elapsed chunk service time decreases 60.83 → 53.23 seconds. Do not add
nested/overlapping Server-Timing durations. Validation/SQL remainder is approximately
0.216 → 0.369 seconds in this fixture. Both the extra checkpoints and their cost
are visible, rather than labelled an increase in connection bandwidth.

Memory samples run independently every 25 ms. Python RSS includes the isolated
server/test runner, excludes the Node SQL child; browser RSS sums Chromium processes.
Short transient peaks can be missed. The storage double does not reproduce TLS or
all SDK allocations. An actual-adapter test verifies the bounded immutable copy and
byte integrity. Global admission lock identities/lifetimes are tested with independent
connection doubles, alongside real disposable SQL service tests; native multi-worker
Postgres failover/concurrency and concurrent real Dropbox memory were not benchmarked.

Raw evidence retained in `output/product-upload-phase2`:
`phase2_baseline-browser.json`, `final-browser.json`, `final-comparison.json`,
`relay-before-transaction-timeouts-browser.json`, and the baseline runtime snapshots.

## Focused checks and finish

**133 tests and 56 subtests passed**, covering the changed relay plus existing
intake, browser recovery, handoff/deduplication, modes, mockups, colour validation
and shared Dropbox adapter. No new regressions remain. Tests explicitly cover:

- Reception overlaps one ordered writer; full storage hash matches original bytes.
- One queued frame, two frame permits, global two-upload and per-intake admission;
  capacity and unsettled writes fail closed without another provider append.
- Lost HTTP/provider ACK, cancellation, checkpoint failure and fresh-service resume.
- Legacy 8 MiB provider acceptance before a lost checkpoint; no duplicate bytes/jobs.
- Exact identity, altered retry blocks, size/alignment, old/new client compatibility.
- Real Chromium reload stays empty, explicit re-selection resumes, finish ACK loss
  finalises exactly once, and upload creates no unintended worker job.
- Virtual-clock deadline measurements: a 325-second progressing request completes
  without retry; a 60-second stall after progress reconciles before 4 MiB fallback;
  15-minute cap, busy reconciliation and six-attempt bounds remain in force.
- SDK clone shares pool/path-root and leaves shared defaults unchanged; retry limits
  and payload identity are verified without a provider request.

`node tests/test_product_upload_state.cjs` passed. The existing benchmark passed for
both versions/profiles, followed by the final timeout-safeguarded run. Known
Starlette/httpx and WebSockets deprecation warnings are unrelated.

Python command:
`python -m pytest -q tests/test_product_upload_relay.py tests/test_product_upload_intake.py tests/test_product_upload_browser_transport.py tests/test_product_upload_handoff.py tests/test_product_upload_modes.py tests/test_product_upload_mockups.py tests/test_mockup_upload_validation.py tests/test_dropbox_integration.py`

Benchmark uses the existing PGlite and explicitly NON_PRODUCTION PSD environment
settings, with `PHASE2_BENCH_MODE=phase2_baseline` or `final`.

Files changed for this completion:
`components/product_uploads/app.js`, `product_upload_api.py`, `product_upload_intake.py`,
new `product_upload_relay.py`, `product_upload_services.py`, `dropbox_integration.py`,
`tests/test_product_upload_relay.py`, `tests/test_product_upload_intake.py`,
`tests/test_product_upload_browser_transport.py`, `tests/test_product_upload_state.cjs`,
`tests/benchmark_product_upload_browser.py`, and this report. Prior local changes
remain present. No dependencies, infrastructure, deployment config or dashboards added.

The remaining limit is browser bandwidth plus provider acceptance and the durable
end-of-request tail. Actual internet/provider/DB connection latency, proxy buffering,
and production concurrency remain unmeasured. A buffering reverse proxy may reduce
overlap. Very slow links can still reach the finite cap and show Interrupted with
File retained. This is a completed local implementation, not a real Dropbox speed
claim or release authorisation. No commit, push, merge, deployment or production
mutation occurred.
