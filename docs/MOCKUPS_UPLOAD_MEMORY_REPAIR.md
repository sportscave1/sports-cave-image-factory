# Mockups upload memory repair — local verification, 10 September 2026

## Confirmed cause and deployment evidence

The clean starting tree was commit `3f429c52bf17b4d14c65924335a761805632d65d`.
The exact screenshot message occurs in the original-artwork preparation path:

`render_mockups_page` → Generate Core Shopify Images → `generate_product_images`
→ `prepare_working_artwork` → `ensure_memory_available` (before opening the source)
or `collect_garbage` → `ensure_memory_available` (after saving the working image).

At HEAD, `ensure_memory_available` raised `MemoryLimitExceededError` whenever whole-process
RSS was at least 430 MiB. This happened independently of upload bytes, image dimensions,
container capacity or available headroom. The UI displayed that exception verbatim.
The exact artwork-specific message was supplied to these two artificial checks; it was
not evidence of a Pillow allocation failure. Without event logs we cannot distinguish
which of the two checks fired for the screenshot.

A read-only reproduction executed the HEAD guard extracted with Python AST, with RSS
mocked to 600 MiB. It rejected the artwork stage before any image was opened. The repaired
pipeline successfully prepares artwork, generates five core images and previews, and
creates a ZIP at the same mocked RSS with 1 GiB available headroom.

The earlier lifestyle fixes are in local history (`f5f3bc8`, `c0e0721`). Render's read-only
list-deploys response for canonical service `srv-d8kl4on7f7vs73dvavv0` reported live deploy
`dep-dagchtht0dsc739ab9rg` at `3f429c5`, finished 9 September 2026 02:50:25 UTC.
`git merge-base --is-ancestor c0e0721 3f429c5` succeeded. Thus the live commit includes the
previous lifestyle fix; that fix left original-artwork and downstream RSS checks intact.
Runtime log retrieval required a selected workspace and was unavailable. No service plan,
actual memory readings for this upload, or live post-repair behavior was verified.

No original Messier artwork was found in the repository. The screenshot is not the source
image. Tests use generated representative fixtures, not an assumed size/dimensions for
that source file. No decoded-image leak is claimed as the cause of the reported event.

## Implementation

- `image_factory.py`: removes the fixed RSS rejection. Existing stage-marker helpers now
  log RSS without rejecting work; this also removes false failures in later previews,
  ZIPs and exports. No replacement RSS constant is introduced.
- Artwork preparation uses the existing host/cgroup v1/v2 headroom budget, including
  constrained parent cgroups. Original dimensions are checked before JPEG draft decoding;
  processing estimates use the drafted dimensions where applicable. Available headroom,
  estimated allocation bytes, reserve and RSS are logged separately.
- File limits remain 20 MiB for artwork and 15 MiB for lifestyle. Supported formats and
  the 25-million-source-pixel limit remain enforced. File bytes, pixel-limit errors,
  budget/allocation failures and unreadable container telemetry have distinct messages.
  No memory error advises a Render upgrade or claims the file exceeds a byte limit.
- In-place EXIF handling avoids an unnecessary full decoded copy. Original artwork remains
  unchanged on disk; its working derivative remains bounded to 2000px and now retains
  supported alpha. Existing 1600px exports, 900px previews, quality settings, and lifestyle
  square-crop behavior are retained. Core output continues its existing RGB behavior.
- Artwork and lifestyle decode work share the existing processing lock. Lifestyle slots
  remain sequential. Decoded resources close explicitly; repeated garbage collection is
  removed from this image pipeline. Session caches contain paths/metadata rather than
  decoded images, and reruns reuse the existing content-signature cache.
- Working artwork and previews are staged before publishing. Lifestyle JPG/WebP/preview
  sets finish encoding before replacement, with backups and rollback on file-commit
  failures. Failed processing leaves existing files intact and allows retries. Staging
  directories are cleaned on success/failure; stable output names avoid accumulating
  obsolete decoded assets. Existing run assets remain available for saving and retries.
- `app.py`: uses a borrowed stream wrapper so closing Pillow images cannot close the
  Streamlit upload needed for reruns/retries. Preview writes are atomic. The fallback
  artwork validator reuses the same processing/cache path. A rejected replacement retains
  the previous valid preview. Memory errors are shown accurately without UI tracebacks.
- Diagnostics include stage, dimensions, mode, measured upload bytes and memory estimates;
  allocation exceptions retain their traceback and cause in logs. No image contents,
  credentials or URLs are added to logs.

## Verification

Commands (repository virtual environment; system Python lacks the dependencies and neither
Python environment has pytest installed, so the repository's unittest suites were used):

```powershell
.venv/Scripts/python.exe -m unittest tests.test_mockup_artwork_memory tests.test_mockup_second_image_upload tests.test_mockup_memory_headroom tests.test_mockup_upload_validation tests.test_mockup_memory_pipeline tests.test_mockup_eight_image_manifest -q
.venv/Scripts/python.exe -m unittest tests.test_mockup_prompt_preview -q
.venv/Scripts/python.exe -m py_compile app.py image_factory.py tests/test_mockup_artwork_memory.py tests/test_mockup_memory_headroom.py tests/test_mockup_memory_pipeline.py tests/test_mockup_second_image_upload.py
git diff --check
```

Results: 71 backend/state/export tests and 33 UI tests pass; compile and diff checks pass.
Run the UI suite in a separate process: combining it with bare Streamlit state tests
produced shared form-context interference (`st.button()` inside `st.form()`); its isolated
run passes. Existing external-write operations in these tests are mocked.

New regression coverage includes original JPG/PNG/WebP, full generation and ZIP at RSS
600 MiB, alpha/EXIF orientation, small compressed files with excessive source pixels,
insufficient headroom before decode, invalid and over-byte-limit input, weak-reference
liveness after repeated preparation, cache reuse, preview failure/retry, all three
lifestyle replacement exports, and rollback after a partial file commit. Existing suites
cover cgroup ancestors/v1/v2, all lifestyle callers, sequential uploads, unchanged JPEG,
WebP and preview pixels, state isolation, stale/failed lifecycle retry, and save manifests.
Liveness checks do not require allocator RSS to return to its starting value.

## Delivery limits

Ready for Nathan to test locally. No push, deployment, production write, database update,
Render setting/plan change or production asset deletion was performed. Deployment is
still required to put this repair live. Runtime budgets are conservative estimates and
cannot guarantee immunity to concurrent allocations or an OS-level OOM kill. The exact
source artwork and the live repaired behavior remain unverified.
