# Auto Editions JPG performance and edition-first archive names

14 October 2026. Isolated Studio task `20261014-2add64bb`.
Base: V12 and V11 sales-first changes, reconciled with Files V4 `09709ea3`.

## Changes

- New archives start with `NNN-of-TOTAL`, followed by artwork, order, unit,
  variant, TEST and the complete immutable job hash. Existing saved paths are
  retained; no historical rename or allocation change.
- JPGs bounded at 64 MiB use one Dropbox upload rather than 8 MiB upload sessions.
  Add/cancel semantics, size/content-hash comparison and revision verification remain.
- Existing order folders skip repeated ancestor creation. New folders retain the
  established automatic creation path.
- A bounded 256 MiB disposable disk cache retains exact validated JPG bytes.
  Every download still checks account access, allocation and Dropbox file identity,
  revision, size and content hash. Cache copies verify SHA-256. Dropbox remains
  the permanent archive; cache loss only causes a normal verified fetch.
- Polling an identified job checks account/allocation without fetching the PSD
  repeatedly. Worker checks current source/approval before and after rendering.
- Independent database/Dropbox identity reads overlap, with at most two threads
  per lookup. Saved-file authentication runs outside the async request thread.
- Stage timings are recorded in job results/server logs, file Server-Timing headers
  and browser console. Popup handoff timing is not popup-ready timing.

## Real provider measurements before release

Real archived allocations: baseline SC3282 Allan Moffat #018 (41,459,441 bytes);
optimized SC3293 Dick Johnson & John French #003 (39,772,684 bytes).
Both 11340 x 8016. Different approved artwork samples, similar file sizes;
these are not a controlled identical-image A/B or complete browser click timings.
The existing worker claimed SC3293 Allan Moffat #019 before the diagnostic worker;
the diagnostic safely stopped rather than executing a duplicate.

| Stage | Baseline ms | Optimized ms |
|---|---:|---:|
| Operator account lookup/access | 3097.586 | 2761.046 |
| Request allocation/source/approval identity | 4434.580 | 3038.361 |
| Prepared asset retrieval | 3644 | 3073 |
| Master decode/copy | 2212.715 | 2679.815 |
| Exact number patch | 2.346 | 2.648 |
| JPG encoding | 589.365 | 621.977 |
| JPG integrity validation | 831.222 | 909.958 |
| Folder preparation | 1802.033 | 226.720 |
| Upload (includes destination conflict check) | 7505.695 | 3025.570 |
| Dropbox saved-file verification | 196.683 | 202.592 |
| Archive and verification total | 9749 | 3693 |
| Render/archive worker total | 17456 | 11389 |
| Final source/approval identity | 4384.278 | 2874.524 |
| Finish database write/audit | 1417.286 | 1425.696 |
| Cold archived download and SHA verification | 2902.816 | 2505.449 |

Baseline enqueue 1975.880 ms and claim 1568.821 ms. Optimized diagnostic used an
atomic exact-job enqueue/claim (1716.581 ms) to avoid competing with the normal
worker; this is **not** a queue-scheduling performance comparison. Production
queue scheduling is unchanged. First-attempt queue duration is instrumented.

Optimized warm verified output copy: 324.447 ms, including current Dropbox
revision verification and SHA-256 checks. Warm prepared assets: 68.213 ms.
Warm re-render produced the identical JPG SHA-256:
`926b71afe6432f6f0f14dae54a86fbd072173e86eb7103f929e2d156805072fc`.
This server-side cache result excludes browser/account/database latency.

Largest measured costs: upload, identity/database round trips, prepared asset
retrieval. JPEG quality=100, subsampling=0, ICC handling, 300 PPI metadata and
all image composition parameters are unchanged. No master is resized or modified.

## Validation before release

55 focused Python checks passed; 9 PGlite durable queue/fencing checks passed.
Actual local Edge desktop/mobile fixture checks passed: immediate feedback
3.1/1.7 ms, correct popup selection, unchanged Orders state, one generation
request, downloads and blocked-popup recovery. These are fixture timings,
not live Dropbox timings. Render topology validation passed.

The in-app browser blocks popup creation; a live popup-ready before/after time
cannot be asserted from it. Keep the existing popup implementation unchanged,
and preserve the separately deployed Files V4 implementation. Live HTTP/client
acceptance and deployment revision are recorded separately after release.

No new infrastructure, schema, mapping, PSD, master, allocation, Shopify,
fulfilment, V11 host/queue or Prodigi changes are part of this patch.
