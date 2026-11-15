# Files Performance V4

Implemented in the existing `sports-cave-files-performance-v1` worktree and
`codex/files-performance-v1` branch, Studio task `20261014-50508219`.
Base `f9059fa0` matched main and Render at the start. No push, deployment, storage
activation, live customer file access or changes in another worktree were made.

## Changes

Generic icons were painted before asynchronous thumbnail requests, and even a
cached thumbnail waited for the intersection observer. Supported images now use
a fixed-size neutral placeholder; valid cached images attach during row creation
before DOM insertion. Uncached images fade in over 90 ms (disabled for reduced
motion); cached ones have no animation. Unsupported files and failed thumbnails
retain their file-type icon. Brief bounded failure caching avoids repeated flashes.
Tests confirm stable geometry, no old-revision thumbnail reuse and four live
browser requests. Existing virtualisation and 120 px near-viewport prefetch remain.

The existing viewer displays the cached grid image while retrieving the screen
representation. When none exists, a small non-blocking loading placeholder replaces
the blank stage. Revision checks now prevent reuse of a previous revision's image
at the same path. Account-namespace changes discard cached thumbnail URLs, failure
entries, folder caches and the embedded viewer. Open stays internal; no helper,
localhost connection, desktop authentication or external application was restored.

The V3 encrypted R2 pipeline now retains provider grid thumbnails separately and
upgrades an entry to screen+thumbnail on first image Open. Grid requests retrieve
only a 256 px provider asset; they never download originals. A failed screen
upgrade preserves a working grid thumbnail. Known unavailable thumbnails return
their icon fallback immediately rather than waiting through a pointless poll.
WebP derivatives use quality 76/80 (grid/screen), with a JPEG encoder fallback;
the API returns the actual MIME type. Processing-version keys invalidate older
encoding versions. Bounds remain 256 encrypted bundles / at most 1 GiB per
namespace, with 30-day expiry and demand-time cleanup; see V3 for full limits.

Confirmed uploads enqueue bounded, optional provider-only thumbnail preparation.
It never delays or changes upload success; duplicate final chunks do not enqueue
twice. No request is queued for incomplete/failed saves or missing configuration.
The download adapter now uses Dropbox's documented revision path instead of the
deprecated separate `rev` argument, retaining returned ID/revision validation.

Auto Editions investigation: its publisher retains a verified local JPG, but does
not carry a Files user's cache scope. No cross-user scope or new generation hook
was invented. Its generation, archives, mappings, allocations and preparation host
are untouched. Grid/upload warmups never retrieve that 35 MB original merely for
a thumbnail. An uncached screen preview can still require V3's one bounded
server-side original transfer when no provider preview is available. PSDs only
use safe provider representations; unsupported PSDs keep the icon/Download path.

## Measurements and acceptance

All numbers below use safe synthetic providers, not live Dropbox/R2. Tests use
actual Chrome/Edge and production HTML, plus actual Pillow/Fernet. The Python
runner strips provider credentials and blocks non-loopback sockets. Raw metrics,
earlier runs and screenshots are in `docs/files-performance-v4-evidence/`.

- Cached thumbnail attached in **0.1 ms** in the final dedicated Chrome fixture,
  before observer callbacks. No measured row layout shift. 33 thumbnail requests
  during two viewport visits plus an error case in a 500-image folder; four live
  requests maximum. Mock server requests awaiting their simulated delay after
  browser abort can overlap (peak eight); these are not eight live browser requests.
- Grid derivatives are at most **256×256**; screen at most **1600×1200**, without
  upscaling provider assets. Four flat/noise encoding fixtures average approximately
  **2.7 KB/grid** and **610 KB/screen**. These are synthetic artwork, not estimates
  of a real catalogue's average. Browser test thumbnail: 660 bytes.
- The padded 35 MiB solid JPEG fixture yields approximately **3.5 KB screen** and
  **6.8 KB encrypted two-size bundle**. It uses one server source transfer; repeated
  reads use none. WebP encoding takes longer than JPEG (roughly 0.2 seconds for that
  fixture, up to about 0.5 seconds for noisy screen images), but runs off the request
  path when a provider representation exists and avoids repeated processing.
- Controlled persistent grid reuse: **3/3 hits across a new Store instance**, no
  provider thumbnail calls, all three current metadata permission checks retained.
  This is not a measured production hit rate. Live storage usage is unknown.

Final paired V3/V4 browser measurements (ms, p50/p95; six folder samples, four image
journeys, so p95 is effectively the observed maximum):

| Action | V3 | V4 |
|---|---:|---:|
| Files launcher click → shell (one sample) | 76 | 139 |
| Cold 2,000-item usable list | 104 / 108 | 118 / 132 |
| Cached folder | 6.5 / 6.5 | 7.5 / 13.8 |
| Uncached folder, 30 ms fixture provider | 60.1 / 61.5 | 69.5 / 75.2 |
| Double-click → image visible | 79 / 94 | 94 / 94 |
| Close/reopen image | 26 / 30 | 29 / 30 |

These do **not** demonstrate a general network or list speedup. Earlier paired
runs were closer (103→104 ms cold list, 6.6→6.4 ms cached folder); all are retained.
The improvement is immediate cached-thumbnail attachment and stable progressive
display. Some final timings are slower and are reported rather than discarded.
They remain within the fixture targets, but real-provider speed acceptance is
outstanding. Final heap medians are 3.78→3.79 MB and script CPU 12.70→14.19 ms;
no CPU/memory reduction is claimed. Scrolling is 16.7/16.8 ms per frame. Exact
archived JPG selection took 150 ms without downloading the original for selection.

Validation: 167 Python tests including V4 encoding/persistence/upload checks;
four complete web-only browser platform journeys; V4 skeleton/cache/failure/
revision/scope/cancellation tests; V3 pending-preview checks; nine PSD-modal
scenarios; live-base Orders popup checks on desktop/mobile; Render topology and
Studio verification. JPG/PNG/WebP, safe PSD fallback, PDF, upload/download,
create/rename/copy/move/delete, selection/search/history and staff checks pass
under fixtures. Source artwork remains unchanged; tests never mutate provider data.

## Storage and release blocker

R2 code existing is **not** evidence of working R2 configuration. The development
process has no `R2_*` or `FILES_PREVIEW_*` environment values and only `.env.example`
is present. Render's read-only service metadata confirms the service/revision but
does not expose environment variables, bucket privacy or encryption validity.
Production cache configuration therefore remains **unverified**, not declared
missing or active. No production credentials were copied into a development preview.

Administrator action before activation:

1. Identify an approved existing private R2 bucket and verify that public R2 and
   custom-domain access are disabled. Confirm existing R2 endpoint and restricted
   credentials without exposing their values in chat/logs.
2. Provision/verify `FILES_PREVIEW_BUCKET`, a unique `FILES_PREVIEW_NAMESPACE`, and
   a valid secret `FILES_PREVIEW_ENCRYPTION_KEY`; set
   `FILES_PREVIEW_PRIVATE_BUCKET_CONFIRMED=1` only after privacy verification.
3. Validate the installed SDK's conditional writes/lease behavior, encryption,
   staff denial, revision changes, restart reuse and bounded cleanup with an
   authorised **non-production** Dropbox/R2 fixture account. Measure actual
   Server-Timing metadata/storage/provider components and cold/warm browser time.
4. Reconcile with the latest completed legitimate release and run combined checks
   before separately activating the persistent pipeline. Until then, V2's
   authenticated provider-thumbnail fallback remains functional.

Another task's `a9270c8b` deployment `dep-db7k81p42hec7399tlgg` was initially
`pre_deploy_in_progress`. After it became live, this isolated branch was safely
fast-forwarded to that legitimate revision without conflicts, overwrites or
running any preparation code. Preservation tests now compare against that base.
V4 is left committed for review/acceptance, **not deployed or activated** because
private storage configuration and real-provider safety/performance are unverified.
No Photoshop host, cloud generation, Design Studio, Developer Studio, Shopify or
Prodigi code is changed by this commit.

Reference: [Dropbox download API and revision parameter](https://dropbox-sdk-python.readthedocs.io/en/latest/api/dropbox.html#dropbox.dropbox_client.Dropbox.files_download).
