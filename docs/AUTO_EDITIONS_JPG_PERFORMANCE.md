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

## Follow-up: live latency beyond rendering

First release: `bdf1e252`, Render `dep-db7l1kugekts73e16icg` live.
Actual Orders click generated SC3294 Kostecki #011, one attempt:
35,688,525 bytes, 11340 x 8016,
SHA-256 `ae77f23a843c538a28fcf20ac6a66e7fb4535fb4de7920284bcb5a90ea8d523e`.
The browser-downloaded file matched; visual inspection confirmed 011/100 and the
original right-hand plaque, border and composition. Existing #001-#007 untouched.

Live worker: 14.226 s (new folder, cold prepared assets). Durable request-to-ready:
23.555 s, excluding start authentication and browser transfer. The connected
browser-control call timed out and lost its click-timing handle; do not claim an
exact click-to-download duration from this run. The automatic file request reached
the server (retention audit); full browser download was then independently verified
through the existing Files Download button. Saved-edition popup route correctly
selected the file; popup creation itself remains blocked by the in-app browser.

Actual stages in milliseconds: authentication 992.917; request identity 2901.987;
first queue wait 1917.010; claim transaction 1710.302; worker identity 2837.274;
master retrieval 3218; decode/copy 2819.984; number patch 2.961; encoding 575.699;
JPG validation 928.832; folder 2221.232; destination lookup 282.330;
upload 3650.754; archive checksum/verification 339.733;
final source/approval identity 2856.692. Totals contain nested stages.

Repeat download through the saved-edition Files route took 21.113 s despite the
byte cache. This exposed remaining database/authentication round trips. Separate
ordinary Files download of the 39.8 MB SC3293 file took 7.593 s; this uses a different
endpoint and is not a before/after cache comparison.

Follow-up implementation (preserving newer Files V5 `c07119e4`):
- Supported Psycopg pool for Auto Editions only: max 3 connections, bounded wait,
  existing SSL/timeouts, health check, transaction rollback and broken-connection
  replacement. No cached permissions or allocation data; V11 queue unchanged.
- Reuse the existing Files 25-minute authenticated Dropbox context.
- Fetch saved job and current allocation in one SQL statement. Full allocation
  identity checks remain; no PSD mapping query is needed for historical archives.
- Remove one duplicate account lookup during download and reuse the same Dropbox
  context for the final identity fence. Account/allocation are still rechecked
  after bytes are prepared.
- Already-retained permanent archives no longer repeat the retention write/audit;
  older expiring files retain the atomic pin operation.

Real read-only Render probe: fresh database connection/query 1396.616 ms;
pooled cold 1429.290 ms; pooled warm 566.401 ms. Identity check cold 2274.549 ms,
warm 1507.010 ms. Intentional SELECT division-by-zero rolled back successfully;
closed connection was discarded and a replacement succeeded. No data was written.
66 focused Auto Editions/PGlite tests passed. Latest Files V5 regression and Edge
popup/Orders preservation checks passed. Studio's full old-base static comparison
still reports inherited unrelated whitespace; this patch's diff check is clean.

Pool semantics: https://www.psycopg.org/psycopg3/docs/api/pool.html
