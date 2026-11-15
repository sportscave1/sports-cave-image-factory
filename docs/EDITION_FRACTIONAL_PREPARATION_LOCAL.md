> Historical stage record. Native comparison and current integration results: [SC3340_NATIVE_COMPARISON_RELEASE.md](SC3340_NATIVE_COMPARISON_RELEASE.md).

# Fractional preparation target — local implementation, 21 October 2026

Continues task `20261020-04713977`, owner
`codex-print-info-20261021-01a15bad`, on its original branch and Studio-approved
base `59b609728b182c6c997f02ed0a8786fff0483095`. The uncommitted resolution
information update is preserved. This subsequent change implements the user's
explicit preparation-sizing authorization. No commit, push, deployment,
supplier submission, allocation, source replacement or live-order mutation.

## Implemented change

`auto_editions_preparation_geometry.py` supplements the existing integer sizing
policy. Successful legacy results are retained; an insufficient result can use
a proportional fractional enlargement to the known supplier raster requirement
when that full canvas fits within the existing 95,000,000-pixel budget.
An over-budget target retains the bounded legacy result and records
`below_target_worker_budget`, rather than claiming target success.

The planner reuses the existing selected-SKU/family mapping, supplier validation
and editor resolution evidence used by the informational task. It never treats
storefront centimetres as verified print geometry. A selected SKU alone, an
exact unit variant, or known cached order-line variants can identify a target.
Missing/unverified SKU evidence retains the old integer policy and an unknown
target. No generic framed A1 target is assigned to an unframed variant.

Masters and approvals are currently shared at product level, including smaller
sizes. Planning therefore covers the largest known supplier requirements within
the mapped families, rather than shrinking a shared master for a smaller order.
Automatic preparation context now includes a deterministic, bounded list of
already-synced order-line variants in its existing read query. No commerce row is
changed and no additional API call is introduced. Unknown sizes/families remain
unverified; meeting one known target does not certify another.

Existing verified supplier canvases already include declared bleed. Known crop
bounds in source coordinates increase the required full-image dimensions;
the source itself is never cropped. `supplier_crop_bounds_px` is optional saved
context evidence, not a guessed value or a new public crop-control endpoint.
Current SC3340 crop and bleed are unknown, so its target remains explicitly an
estimate before supplier crop/bleed.

The fractional path constrains proportions with Photoshop's existing
`BICUBICSMOOTHER`, supplying a width and allowing Photoshop to round the height.
The rounded output is checked against the pinned plan; a rounding disagreement
fails explicitly. Existing successful integer resizes retain their original
two-dimension Photoshop call. No AI enhancement, sharpening or colour-processing
change is included. Document resizing scales its layers/masks/text; the existing
number-bound scanning and merged-patch cropping then measure the resized layout.
The JPEG compositor and encoder are unchanged: quality 100, 4:4:4, existing ICC
handling and 300 DPI metadata.

## Version and cache boundaries

The new plan records policy version `selected-sku-fractional-v1`, source/output
dimensions, selected reference specifications, required dimensions, scale,
legacy/manual scale choice, crop/bleed uncertainty, budget and target result.
It is embedded in `preparation_geometry` and therefore in the existing full
manifest fingerprint, prepared asset paths and generated job identity.

Both local finished-package recovery and package reuse compare current target
and policy, not just an integer scale. Fresh package intake checks the same
current plan before any storage publication when a supplier target is known.
An old undersized package cannot be silently reused for that preparation.
Explicit manual integer choices remain bound in their plan; automatic Jake
preparation retains its existing 4× policy/result.

Historical manifests remain accepted under their original validation rules.
No source, archived file, fulfilled job, approval or layout row is rewritten or
invalidated, and no automatic migration/requeue is performed. Existing approved
masters remain historical versions until an authorized new preparation is run;
this local patch does not refresh production records. Retained historical
download paths still use their exact pinned job/archive, with unchanged integrity
checks. A new preparation gets a new identity and must satisfy the existing
approval/readiness rules; raster sizing does not make it print-ready.

## SC3340 comparison status

The user explicitly chose **finish code; leave native comparison pending** after
the existing native guard reported running companion PID 9468 and less than its
4 GiB free-RAM minimum. The companion was not stopped, its processor lock was
not bypassed, and Photoshop was not invoked. Consequently there is **no revised
SC3340 JPEG or native visual/memory/runtime result** in this task.

| Measurement | Existing archived-original copy | New planned preparation, not yet executed |
|---|---|---|
| Edition | 059/100 | 059/100, no new allocation |
| Pixels | 7016 × 4961 | 9933 × 7024 |
| Enlargement | 1× | 1.415763968072976× by width, proportional rounded height |
| Pixel budget | 34,806,376 | 69,769,392 / 95,000,000 |
| PPI at 841 × 594 mm | 211.8977 × 212.1367 | 299.9978597 × 300.3528620 (estimate) |
| JPEG bytes | 15,555,990 | Not measured; no revised file exists |
| Colour | Existing RGB/sRGB ICC retained | Same pipeline required; native result not measured |
| DPI metadata | Existing 300 × 300 | Existing encoder remains 300 × 300 |
| Native runtime / peak RSS | Not newly benchmarked | Pending |
| Equivalent-print-scale visual review | Existing file preserved | Pending: faces, text, signatures, number/plaque/masks |

9933 × 7016 is the configured A1 integer recommendation. The source has a slightly
different aspect ratio, so reaching both dimensions proportionally needs
9933 × 7024. Forcing 9933 × 7016 would change proportions or crop the image.
The small rounding discrepancy around 300 PPI follows the existing supplier
integer recommendation, not a lowered quality threshold.

The existing JPEG was read and its SHA-256 remained
`b255bdcf1e0f9309d1b92a9b839a1a0cf465eb76f18ff874eea4180eb0655c42`.
Local evidence `output/fractional/sc3340-comparison-plan.json` explicitly records
the revised JPEG, size, native runtime, peak RSS and visual comparison as null.
It contains the complete target plan and planned PPI alongside actual original
metadata. It is not a generated print file.

The approved task base predates later source-role/hidden-number recovery work
used by SC3340's deployed preparation. That later reviewed source handling must
be preserved during eventual combined integration; no original layers were
guessed, renamed or hidden in this task. The pending real-source trial must use
that reviewed handling, not bypass it or enlarge the archived JPEG.

## Focused validation

Changed preparation files: `auto_editions_preparation_geometry.py`, manifest
validation in `auto_editions.py`, `auto_editions_onboarding_api.py`,
`auto_editions_setup_api.py`, `scripts/prepare_auto_editions.py`,
`scripts/photoshop/prepare_auto_editions.jsx` and
`scripts/studio/auto_editions_local.py`. `auto_editions_resolution.py` retains
fractional provenance and displays budget shortfalls. Tests are in
`tests/test_auto_editions_fractional.py`, with narrowed encoder-preservation
assertions in the prior resolution test and new model cases in the V19 JSX test.

```powershell
$env:PYTHONPATH='C:/Users/hello/.codex/tmp/print-quality-metrics'
python -B -m pytest -q tests/test_auto_editions_fractional.py tests/test_auto_editions_resolution.py tests/test_auto_editions.py tests/test_auto_editions_preparation_host.py tests/test_auto_editions_native_v19.py tests/test_auto_editions_api.py tests/test_auto_editions_onboarding_api.py tests/test_auto_editions_package.py tests/test_auto_editions_cloud.py
node tests/test_auto_editions_native_v19.cjs
```

Result: **123 passed, 1 skipped** in the focused Python run, with one existing
intentional duplicate ZIP-member rejection warning. The JSX model and all six
resolution UI desktop/mobile scenarios passed. The final metadata-null handling
was additionally checked with the focused fractional unit file. Studio static
verification and `git diff --check` pass. Native Photoshop checks remain pending.

The Python focused run covers SC3340 sizing, Jake 4×, sufficient native sources,
unknown SKU, shared sizes, known crop/bleed, over-budget results, versioned cache
selection, stale intake before publish, manual choice binding, old manifests,
fractional information and synthetic compositor/encoding/placement integrity.
The JSX model covers a constrained 1.5× resize, proportional number/plaque/mask
coordinates, remeasured patch region, unchanged font/profile, 100 patch exports,
integer resize compatibility and owned cleanup. It is explicitly a control-flow
model, not native Photoshop pixel, appearance, timing or memory evidence.

The existing resolution UI desktop/mobile suite also passes after a test-only
timing fix: it now waits for the existing asynchronous download acknowledgement
before asserting that its link is enabled. Product download behaviour is unchanged.

Warm target planning measured approximately 24 microseconds per call over 10,000
calls. Larger prepared assets will cost more to process; actual runtime and peak
memory are unmeasured. A 95 MP arithmetic limit alone does not prove safe RAM use.
No full application or production preview was started.

## Remaining verification

When the native comparison is separately resumed, first establish exclusive
Photoshop access and adequate memory using the existing guard. Use a new local
output directory, the pinned verified source with its reviewed source roles and
colour policy, and reference edition 059. Retain the archived JPEG and original
PSD hashes. Measure sampled Photoshop/Python peak RSS, runtime and resulting
encoded file metadata; compare faces, text, signatures and number/plaque placement
at equivalent physical print scale. Do not publish or replace existing files.

The actual Prodigi uploaded asset and crop remain unverified. Neither this sizing
change nor the future comparison proves why Prodigi previously gave a particular
rating, recovers original photographic detail, or guarantees Excellent quality.
