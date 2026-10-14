# Files Performance V5 — measured backend work reduction

## Release and access status (14 October 2026)

Worktree: `C:\Dev\SportsCaveWorktrees\sports-cave-files-performance-v1`.
Branch: `codex/files-performance-v1`; Studio task `20261014-50508219`, owner
`codex/files-performance-01a1391d`. Started from `09709ea3`, which matched main
and Render. V2–V4 are integrated, including web-only Open and V4 derivatives.

During this task another release advanced main and the canonical Render service
`sports-cave-os` to **bdf1e252cd7779b973498299dadb9b93243abb34**, deployment
`dep-db7l1kugekts73e16icg`, live at 09:55:16 UTC. It changes Auto Editions JPG
archive performance. Those concurrent changes were not edited, overwritten or
deployed by this task. V5 remains isolated on the prior reconciled base; rebase or
merge the latest legitimate main and retest before integration. No deployment,
push, bucket creation or cache activation was performed here.

The user authorised read-only inspection of Nathan's Render workspace. The
thumbnail route's HTTP latency/count query returned empty data; a filtered
`FILES_PREVIEW` log query returned no entries. These results do not establish
whether the cache is enabled. Available Render tools do not expose a read-only
environment-variable listing. No configured non-production Dropbox/R2 account
was found locally, and no production credential or customer artwork was used.
**Real Dropbox/R2 timing, active cache state, hit rates and storage consumption
remain unverified. Three largest real-provider bottlenecks cannot honestly be
ranked from this evidence.**

## Demonstrated costs and changes

1. V4 thumbnail-only preparation encoded a screen WebP and then discarded it.
   V5 explicitly requests thumbnail-only processing, sizes the decode accordingly
   and encodes only the 256 px asset. Screen preparation still produces both sizes.
   This repairs a measurable V4 CPU cost without changing the output format/version,
   original artwork, provider selection or source-transfer policy.
2. V4 durable hits downloaded, decrypted and decoded the bundle repeatedly, even
   within a short revisit. V5 admits verified durable bytes to the existing bounded
   memory cache. Thirty repeated fixture reads now require one storage GET instead
   of thirty. Current Dropbox metadata/access checks still run on **all thirty**.
   Cache lifetime is at most 30 seconds and never exceeds the durable expiry;
   bounds remain 128 representations / 32 MiB. Expired entries are swept on insert.
3. No third provider bottleneck is claimed. Metadata latency and serialized R2
   lease/cleanup operations remain plausible costs requiring real traces. Neither
   permission checks nor the distributed storage bound were weakened to reduce them.

Memory keys include the Store instance as well as the existing verified asset
identity/representation. Configuration or encryption-key rotation obtains another
Store and cannot reuse prior bytes. User/root/file-ID/revision/processing-version
isolation remains intact. Server-Timing now labels a memory hit separately; no
artwork name, token or identity is added to telemetry.

V4's immediate thumbnail attachment, placeholders, four live requests, small
viewport prefetch, cancellation, virtualisation, navigation/search/selection,
embedded previews and upload warmup are unchanged. No visual effect or helper
was introduced. Only the preview cache service is changed in application code.

## Measurements — local fixtures, NOT real Dropbox/R2

Raw evidence is in `files-performance-v5-evidence/`. Pipeline measurements use
real Pillow/Fernet with synthetic metadata and in-memory S3, no network latency.
The 30 encoding samples alternate V4/V5 order. Storage measurements include the
initial read plus 29 repeated reads of a 600 KB representation.

| Operation | V4 p50 / p95 ms | V5 p50 / p95 ms |
|---|---:|---:|
| 256 px noisy JPEG thumbnail encoding | 27.63 / 27.97 | 14.43 / 15.06 |
| Verified durable representation read | 5.08 / 5.46 | 0.018 / 0.207 |

Thumbnail encoding median fell approximately 48%. Storage GETs fell 30→1 (29/30
memory hits after first access); metadata calls remain 30. No additional Dropbox
requests were eliminated by V5. This does not predict live end-to-end latency.
The before-edit run is retained separately; no slow samples were discarded.

The browser suite uses actual Chrome and production HTML, synthetic network
responses, six folder samples and four preview journey samples. Small-sample p95
is effectively the observed upper tail, not a reliable production percentile.

| Browser action | V4 p50 / p95 ms | V5 p50 / p95 ms |
|---|---:|---:|
| 2,000-item cold usable listing | 105 / 107 | 106 / 109 |
| Folder shell | 25.5 / 26.8 | 24.6 / 27.2 |
| Cached folder | 7.1 / 7.9 | 6.6 / 7.3 |
| Uncached folder (30 ms simulated provider) | 57.1 / 66.6 | 56.1 / 61.6 |
| Open preview journey | 76 / 94 | 77 / 94 |
| Close/reopen preview journey | 28 / 30 | 29 / 30 |
| Search | 1.7 / 2.5 | 1.4 / 1.7 |
| Selection | 0.3 / 0.3 | 0.3 / 0.4 |

Launcher click-to-shell: 118→100 ms (one sample each). Warm popup reopening uses
zero further listings. Cached thumbnail attaches in 0.1 ms before observer work;
33 requests across the dedicated 500-JPG fixture, four live requests, no layout
shift. Cold thumbnail network time is prescribed at 150 ms, not measured Dropbox
time. Exact archived JPG selection took 142 ms without downloading its original.
Scrolling p50/p95 is 16.7/17.0 ms; 2,000 entries render 56 rows / 559 DOM nodes.
Median heap 3.78→3.77 MB and script CPU 12.72→12.52 ms do not demonstrate a
meaningful frontend improvement; frontend production code is identical.

A separate four-sample standalone viewer run worsened 86/88→96/213 ms. An
interleaved 20-per-version image-load check (40 ms fake response) gave
46.4/49.4→46.9/59.5 ms. Both results are retained. There is no demonstrated
frontend speedup or frontend code change to explain the slower samples. The
broad harness performs explicit Original only on the after side: its four extra
requests are test actions, not repeated ordinary-preview downloads.

The padded 35 MiB synthetic JPG prepares in 201.5 ms locally, produces a 3,494-byte
screen and 6,756-byte encrypted bundle. Twenty warm requests require zero source
downloads and all twenty metadata checks. This flat image tests large streaming,
not realistic artwork complexity. PSD provider-preview and unavailable fallback
tests pass; real PSD preview latency is unknown. No layered PSD is transferred
or reconstructed. Ordinary preview never downloads originals to the browser.

## Persistent storage and administrator action

Activation is **not verified and not performed**. Local configuration names are
absent (see `local-config-status.json`). Production presence is unknown, not
asserted missing. Run `python scripts/files_preview_status.py` in the intended
service environment for a read-only, value-free presence/key-format report.
It makes no network call and does not certify bucket privacy or permissions.

An administrator must verify these existing configuration names, without posting
values into the chat: `FILES_PREVIEW_BUCKET`, `FILES_PREVIEW_NAMESPACE`,
`FILES_PREVIEW_ENCRYPTION_KEY`, `FILES_PREVIEW_PRIVATE_BUCKET_CONFIRMED`,
`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and `R2_ENDPOINT` or `R2_ACCOUNT_ID`.
The encryption key must be a valid Fernet key stored as a secret, shared consistently
by service instances. Use a separate namespace/key for safe non-production testing.
Only set the private-bucket confirmation flag after the following checks pass:

- Existing approved bucket has no public domain/r2.dev exposure or public policy;
  credentials have the intended bucket-scoped read/write/list/delete rights.
- In an isolated synthetic namespace, validate encrypted GET/PUT, conditional
  If-None-Match/If-Match behavior, concurrent lease exclusion, expired-lease
  takeover, renew/release fencing, restart recovery and cleanup pagination.
- Exercise permission revocation, other-user denial, source revision changes,
  R2 outage/write failure and cooldown; verify Download still works independently.
- Confirm actual cold/warm Server-Timing (`metadata`, `storage`, `provider`,
  `memory`), first usable image and browser transfer/decoding with approved
  representative JPG/PSD files. Record the environment and sample counts.
- Check lifecycle/retention and key rotation recovery before activating. The code
  never provisions a bucket or changes public policies. Keep the feature disabled
  if these checks are unresolved; the existing V4 nonpersistent fallback remains.

Retention remains 256 encrypted bundles, maximum 4 MiB each / 1 GiB per namespace,
30-day expiry, demand-time cleanup under the serial writer lease. Synthetic
flat/noise samples average 2.7 KB small and 610 KB screen before bundle overhead.
Actual occupancy, eviction rate and hit rate are unavailable, so expanding the
budget would be speculative. A 500-file working set can exceed the 256-bundle
bound and should be measured before changing policy. Cleanup only touches preview
assets, never archived JPGs or original masters.

Successful uploads retain V4's asynchronous bounded provider-only warmup. Auto
Editions has no Files user scope at its publisher; no new cross-user cache or
second source transfer hook was added. Its already validated representation can
only be reused after defining an authorised Files scope. The concurrent archive
performance release belongs to another task and is preserved for later integration.

## Acceptance and release decision

- 172 offline Python tests pass, including encryption, lease/cleanup bounds,
  restart, expiry, revision/permission denial, failure handling, uploads, memory
  bounds/configuration isolation and current metadata checks on memory hits.
- Four web-only browser platform journeys pass: raster/PSD/PDF, unsupported
  Download, Open actions, create/rename/copy/move/delete, search, upload/download,
  cancellation and permissions; no Files helper requests or extra preview windows.
- Large-folder, stable/lazy/cached thumbnails, preparation polling and revision
  checks pass. Orders desktop/mobile exact-JPG selection and nine shared PSD-modal
  scenarios pass. Shared Photoshop/Design Studio code is untouched.
- Render topology validation passes. Studio static/security verification is
  recorded separately for the committed snapshot.

Ready for isolated code review, **not production cache activation or deployment**.
Real-provider acceptance/storage verification remains blocked by environment
access, and latest main has advanced. Reconcile and retest against the legitimate
release revision before deploying. Original artwork, Auto Editions generation,
allocations/mappings, Design/Developer Studio, Windows preparation host, Shopify
and Prodigi were not changed by V5.
