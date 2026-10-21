> Historical stage record. Native comparison and current integration results: [SC3340_NATIVE_COMPARISON_RELEASE.md](SC3340_NATIVE_COMPARISON_RELEASE.md).

# Edition output resolution information — local review, 21 October 2026

This records the completed informational-only stage. The subsequent authorized
preparation change and its deferred native comparison are documented in
[EDITION_FRACTIONAL_PREPARATION_LOCAL.md](EDITION_FRACTIONAL_PREPARATION_LOCAL.md).

Task `20261020-04713977`, owner `codex-print-info-20261021-01a15bad`.
Branch `codex/task/editions-edition-print-resolution-information-and-n-20261020-04713977`.
Studio-approved base: `59b609728b182c6c997f02ed0a8786fff0483095`.
Uncommitted; no push, release, supplier submission or live-order mutation.

## Change and scope

`auto_editions_resolution.py` derives informational resolution reports from the
existing immutable job manifest and actual exported dimensions in its result.
It writes neither record. Source canvas, prepared/exported pixels, preparation
scale and native-canvas/exported PPI remain distinct. Missing legacy provenance
is unknown. Neither source canvas dimensions nor enlargement establish original
photographic detail. DPI metadata is displayed separately and never used as
effective PPI.

SKU lookup reuses `print_specifications.for_variant` and its existing
`verified` / `_geometry` supplier checks. When full certification is incomplete,
the existing exact-SKU editor evidence provides the A1 dimensions and 300 PPI
recommendation. Storefront centimetres never substitute for a supplier canvas.
Unframed variants cannot inherit framed A1 evidence. No supplier configuration,
threshold or mapping is changed. The supplier's recorded integer pixel target
handles its own rounding (9933 × 7016 at A1), without inventing an Excellent
rating boundary or lowering the configured recommendation.

The existing verified registry defines `printable_mm` as the complete supplier
canvas including declared bleed. Known crop rectangles are measured in exported
pixels and evaluated against that whole canvas; bleed is not added twice.
Current job records contain no actual supplier crop/zoom evidence, so the live
read path labels reports as **estimates before supplier crop**. Legacy editor
evidence also has unknown bleed, explicitly disclosed. There is no new crop
capture form, supplier request or asset-upload integration.

Ready-state, status and saved-location responses add `resolution_info`. These
use already-read metadata: no additional database query, source retrieval,
image decode, renderer call or persistence. Malformed or unavailable evidence
returns an informational unknown state, without blocking existing actions.

The standalone download page and existing Files output area display the same
report. Enlarged outputs show their enlargement and native-canvas PPI in the
compact summary. The Files report is tied to the exact selected archive and
disappears when another file is selected. TEST remains explicit; meeting the
resolution recommendation never grants readiness or supplier approval.

The manual fulfilment selected-line summary displays the selected SKU's known
recommendation and an unknown-file notice. A generated file's PPI is never
attributed to an unobserved manual upload. Existing QA questions, enabled
actions, completion blockers, overrides and their audit records are untouched.
Below-recommendation advice points to the existing Open PSD action for source
review or an owner review of a smaller print size. It performs neither action.

## Protected behaviour and selection audit

No edits to the renderer/compositor, ICC or colour assignment/conversion,
Photoshop preparation/resizing, JPEG quality/subsampling, DPI metadata,
worker memory limit, number placement, filenames, allocations, mappings,
archive retention, original download implementation or fulfilment mutations.

The print download already verifies the pinned archive identity, byte count
and SHA-256; cache copies are checksum-verified as before. Files Download and
Copy Original select `/api/auto-editions/file` for the pinned edition, not a
preview. Copy Original retains the existing native-size PNG clipboard conversion;
Download retains the exact archived JPEG bytes. Preview and upload code was
inspected; no proven preview-selection defect warranted a functional change.
Manual selection in Prodigi is outside the recorded application chain.

The task base predates the later inspected `9c86ea458` release. Its image
encoding is the same; that later revision includes separate PSD/alpha guards
and Files changes. Those changes were not copied into this task. Future approved
integration must preserve them when combining this informational patch.

## Existing affected output (no regeneration)

| Evidence | SC3340 Kobe/Jordan | SC3334 Jake Bauers |
|---|---|---|
| Preparation | `8125a810…`, native 1× | `e497f79b…`, layered enlargement 4× |
| Source canvas | 7016 × 4961 | 2835 × 2004 |
| Prepared/exported | 7016 × 4961 | 11340 × 8016 |
| Exported PPI at 841 × 594 mm | 211.9 × 212.1 | 342.5 × 342.8 |
| Native-canvas PPI at that size | 211.9 × 212.1 | 85.6 × 85.7 |
| Resolution recommendation | Below 300 PPI recommendation | Enlarged raster meets configured recommendation |
| Supplier placement | Estimate; actual asset/crop outstanding | Estimate; actual asset/crop outstanding |
| Readiness | Existing TEST / NOT PRINT READY | Existing TEST / NOT PRINT READY |

The existing SC3340 Downloads copy was read for metadata and SHA-256 only. Its
before/after hash equals the archived job's expected hash:
`b255bdcf1e0f9309d1b92a9b839a1a0cf465eb76f18ff874eea4180eb0655c42`.
It remains 15,555,990 bytes at 7016 × 4961, with its existing ICC and 300 DPI
metadata. Edition 059 was not regenerated, changed or reallocated. Evidence:
`output/resolution/sc3340-existing-original.json` (local, ignored output).

The 2048 × 1448 chat representation remains a different file representation;
its reduction point and whether it was ever selected in Prodigi are unproven.

## Verification

Before edits, the renderer/API/cloud/quality/print/speed suite:
**86 passed, 9 skipped**.

Final Python command:

```powershell
python -B -m pytest -q tests/test_auto_editions_resolution.py tests/test_auto_editions_print.py tests/test_auto_editions.py tests/test_auto_editions_api.py tests/test_auto_editions_speed.py tests/test_auto_editions_cloud.py tests/test_auto_editions_quality.py tests/test_auto_editions_asset_cache.py tests/test_files_originals.py tests/test_auto_editions_onboarding.py tests/test_auto_editions_package.py tests/test_auto_editions_reliability.py tests/test_print_jpg.py tests/test_print_shared_master.py tests/test_fulfilment_handoff.py tests/test_orders_prodigi_loading_repair.py
```

Result: **185 passed, 17 skipped, 5 subtests passed**. One existing intentional
duplicate ZIP member warning from the package-rejection test. New tests include
native SC3340 geometry, Jake's enlargement, sufficient native raster dimensions,
unknown legacy provenance, unknown/invalid crop, known crop and nonzero bleed,
SKU isolation, missing configuration, retained-history reporting without enqueue,
same-byte-count preview rejection, encoded byte/ICC/DPI/subsampling equality,
number-region preservation and unchanged download/readiness/override guards.

Browser commands (bundled Playwright via NODE_PATH):

```powershell
node tests/test_auto_editions_resolution_ui.cjs
node tests/test_auto_editions_internal_ui.cjs
node tests/test_files_originals.cjs
```

All passed. Six new desktop/mobile scenarios exercise native/enlarged/sufficient
reports, TEST and estimate labels, unchanged original bytes/names, exact copy URL,
selection isolation and viewport bounds. Existing tests cover Orders continuity,
download handoff, exact archive selection, actual native clipboard pixels,
original formats, preview isolation and permission failures. These use standalone
synthetic fixtures, not application startup or production accounts/data.
Screenshots: `output/resolution/download-*-*.png`, `files-*-*.png`.

Warm arithmetic/report generation measured ~22 microseconds per call over 10,000
calls, with ~1.6 KB added JSON for SC3340. Static supplier files are cached.
No added image memory, network request or database round trip. No full-application
or production preview was started. `git diff --check` passes.

## Remaining manual verification

In the existing Prodigi order/draft editor, inspect without submitting:

1. Confirm product/SKU and print area (recorded dispatch expectation:
   GLOBAL-CFP-A1, no mount, 841 × 594 mm in landscape).
2. Record the uploaded asset's pixel dimensions and identity. Compare with the
   archived original; a filename alone does not establish identical bytes.
3. Record crop bounds/zoom, orientation, bleed and displayed recommended pixels
   and quality rating. Capture this evidence for both SC3340 and SC3334.
4. If the uploaded asset differs, review selecting the existing archived original.
   If the native original is insufficient, review genuinely better source detail
   or a smaller print size. Metadata changes/interpolation cannot recover detail.

This verification remains outstanding. There is no claim about the exact
Excellent threshold and no guarantee of a rating. No functional change is
proposed or included; supplier capture/integration would require a separate scope.
