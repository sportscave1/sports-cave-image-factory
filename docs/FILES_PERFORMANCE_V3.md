# Files Performance V3 — private persistent previews

## Status and isolation

Implemented locally in `C:\Dev\SportsCaveWorktrees\sports-cave-files-performance-v1`,
branch `codex/files-performance-v1`, Studio task `20261014-50508219`, owner
`codex/files-performance-01a1391d`. No push, deployment, production credential use,
production storage mutation, or customer-file testing was performed.

At the start, HEAD, origin/main and canonical Render service
`srv-d8kl4on7f7vs73dvavv0` were all `a1058ce0`, containing V2. During this task another
release made `069bb9b3` live (`dep-db7jlq67bikc73d3ju7g`). This worktree was safely
fast-forwarded to that revision without conflicts or overwriting local work.
Its shared Files popup and Orders click improvements are preserved and retested.
V3 remains local; neither release above was deployed by this task.

## Findings

V2 already makes the browser shell, virtualized lists, selection and navigation
fast. Its server preview cache is process-local and expires; it does not provide
durable prepared artwork across process restarts. Dropbox's documented thumbnail
limits exclude images above 20 MB and do not promise arbitrary layered PSD
rendering. A small browser icon cannot fix that provider limitation.

The existing repository uses R2 through `services/r2_storage.py`. V3 reuses that
SDK configuration without changing the shared module, adding a storage provider,
or introducing a Supabase schema. No suitable authorised non-production provider
environment was established. Actual Dropbox/R2 latency, throughput and permissions
against a real test account remain unverified. The timing numbers below are
strictly synthetic acceptance measurements.

## Implementation

- `services/files_preview_cache.py` prepares a screen image (up to 1600×1200) and
  a grid thumbnail (up to 256×256). The processing version includes both sizes.
  Provider representations retain their available resolution; they are not upscaled.
- Each key includes deployment namespace, bucket, current authorised user, root,
  verified Dropbox ID, verified revision and processing version. The API checks
  the session/Files permission first, then fetches current source metadata before
  any durable or transient cache read. Changed revisions return 409. Moved,
  missing or inaccessible files cannot be served from an old asset.
- Derivative bundles are encrypted with Fernet and stored only in an explicitly
  configured private R2 bucket. The browser receives authenticated image bytes,
  never a bucket URL, signed storage URL, access token or encryption key. Responses
  are private/no-store. Source originals and credentials are never persisted.
- Existing Dropbox previews are returned immediately; the exact same bytes go
  to the persistence worker. A first open does not wait for a storage write or
  polling interval when the provider already has a preview.
- If no provider representation exists, a selected raster may be streamed once
  by immutable ID and revision into a bounded server spool, decoded, and discarded.
  Only the small derivative reaches the browser. The source transfer metadata and
  byte count must match. Original download and explicit full-resolution inspection
  remain separate existing actions.
- PSDs only use a provider-supplied flattened representation. No PSD layer parser,
  Photoshop launch, master-preparation invocation or PSD-original download is added.
  Unsupported PSDs keep the icon and accurate preview-unavailable/Download state.
- Folder scrolling never queues original preparation. Thumbnail misses retain
  V2's visible-first provider path; opening an artwork prepares both durable sizes.
  No catalogue sweep is performed.
- At most eight pending requests and one decoder per process; a conditional R2
  lease serializes preparation across instances in the configured namespace.
  Same-revision jobs recheck the store after acquiring the lease. Conditional
  renewal/release fences stale workers. SDK connection pools are reused.
- Browser 202 responses show preparation status with cancellable, bounded polling.
  Closing or switching stops obsolete polling. Storage failures have a bounded
  cooldown so polling cannot repeatedly download the same large original.
- `Server-Timing` separates source metadata, storage and provider retrieval.
  `X-Files-Preview-Cache` distinguishes hit/preparing/provider-thumbnail. Safe worker
  logs record ready/unavailable and elapsed time without filenames or secrets.

## Bounds and storage configuration

The feature is disabled unless all four explicit settings are present:

| Setting | Required meaning |
|---|---|
| `FILES_PREVIEW_BUCKET` | Existing private R2 bucket selected for this application |
| `FILES_PREVIEW_PRIVATE_BUCKET_CONFIRMED=1` | Operator has verified no public R2/custom-domain access |
| `FILES_PREVIEW_NAMESPACE` | Stable, unique installation/tenant namespace |
| `FILES_PREVIEW_ENCRYPTION_KEY` | Secret Fernet key, provisioned through the existing secret management process |

It uses the existing R2 endpoint/access credentials. This task did not set any
production values. Missing configuration retains V2; invalid enabled configuration
fails closed. Test the deployed boto3 version's conditional PutObject support
(`IfMatch` and `IfNoneMatch`) in non-production before activation.

Each encrypted bundle is capped at 4 MiB. Demand-time cleanup reserves room before
every write and retains at most 256 bundles (at most 1 GiB) per namespace across
processing versions. Successful assets expire after 30 days; negative results
after 30 seconds. Old revisions cannot be served once current metadata changes,
and are eventually evicted. Idle expired objects are physically removed on the
next preparation, not by an automatic scheduled job. A bucket lifecycle rule on
the isolated prefix can provide idle-time deletion during approved configuration.
Do not apply lifecycle/deletion rules to other R2 objects.

Original preparation is bounded at 100 MiB, with 4 MiB in-memory spool then a
temporary disk file; raster decoding caps are 80 megapixels for JPEG and 32
megapixels for PNG/WebP. One decoder bounds memory pressure. These bounds may
exclude some artwork; originals remain downloadable and unchanged. First-ever
preparation of a 35 MB image can still take the complete server-side Dropbox
transfer time. This release does not claim a subsecond first preview in that case.
No print-proof colour fidelity claim is made for display derivatives.

## Measurements

Raw evidence: `docs/files-performance-v3-evidence/`. Browser fixtures block
unrecognised network destinations. Python runner strips inherited credentials and
denies outbound sockets. Actual Chrome/Edge, production HTML/JS, Pillow and Fernet
are exercised; provider responses and storage are fake.

Final paired browser run compares live base `069bb9b3` with V3. Values are ms,
p50/p95 unless stated. Folder groups have six samples; preview journeys four, so
their reported p95 is effectively the sample maximum, not a production percentile.

| Journey | Before | After |
|---|---:|---:|
| Files launcher click to shell (one sample) | 83 | 97 |
| Shell inside 2,000-file fixture | 24.5 / 25.7 | 24.7 / 30.9 |
| Cold usable 2,000-file list | 105 / 111 | 107 / 111 |
| Cached folder | 6.8 / 7.0 | 6.8 / 7.3 |
| Uncached folder (30 ms fake provider) | 54.5 / 57.8 | 53.7 / 59.2 |
| Selection | 0.3 / 0.4 | 0.3 / 0.4 |
| Local search | 1.7 / 2.4 | 1.5 / 2.4 |
| Double-click through image visible | 76 / 94 | 93 / 94 |
| Close/reopen preview | 29 / 31 | 29 / 31 |

Do not describe this table as a demonstrated browser speedup. V2 behavior is
preserved; some samples are slower. Earlier paired runs are retained, not discarded.
The cold preview median moved by approximately one animation frame, so an
additional interleaved 20-per-version measurement isolated the actual image load
event, alternating execution order with the same 40 ms fake response. V2 was
52.3/62.7 ms; V3 48.7/61.8 ms. This does not establish a meaningful application
speedup or reproduce a material viewer regression. The displayed shell and cached
navigation remain comfortably inside their targets under these fixtures.

Both versions render 56 visible rows / 559 DOM nodes for 2,000 entries. Final
browser heap medians are approximately 3.77 MB versus 3.81 MB; script CPU medians
12.81 versus 12.76 ms. No CPU/memory improvement is claimed. Scrolling is approximately
16.7 ms/frame. Thumbnail concurrency remains four. Warm Files reopening performs
zero additional folder listings. Exact saved-edition selection took 147 ms in the
final paginated fixture, before the full folder finished and without an image read.

The preparation fixture uses a valid 4000×3000 JPEG padded to 36,700,160 bytes;
it tests large streaming, not difficult artwork complexity. The resulting screen
is 30,629 bytes and the encrypted two-size bundle approximately 57 KB. One source
download prepares both sizes; a new Store instance and 20 subsequent authorised
reads make zero additional original or thumbnail requests, while retaining all
20 current metadata checks. Local preparation is around 80–100 ms and local warm
decrypt/serve processing below 1 ms; **these exclude all Dropbox/R2 network time**.
The separate browser pending-response fixture reopens in 0.5 ms with no image
request and continues animation frames while preparation is pending.

V2 could fail ordinary previews for large images outside Dropbox thumbnail
support. V3 adds durable preparation for eligible rasters; it does not turn an
unavailable V2 preview into a fabricated before/after latency percentage. Real
provider request reduction and cold/warm latency must be measured after safe
configuration using Server-Timing and browser network traces.

## Acceptance and integration

- 156 offline Python tests: V2 contracts plus 18 new cache/API tests, including
  encryption, identity isolation, permission denial, revision invalidation, moved
  files, duplicate jobs, lease fencing, cleanup bounds, storage failure cooldown,
  provider reuse, 35 MiB raster and PSD no-original fallbacks.
- Four browser platform journeys: JPG/PNG/WebP/PSD, PDF worker rendering,
  unsupported Download, all Open actions, close/reopen, search, selection, uploads,
  downloads, create/rename/delete/copy/move, permissions and zero Files helper calls.
- V3 browser preparation/cancellation/revision/permission checks and interleaved
  image benchmark pass. Full performance browser acceptance passes against the
  reconciled base.
- Nine shared PSD-modal scenarios and Auto Editions setup regression pass.
  Latest live Orders popup regression passes on Edge desktop/mobile, preserving
  filters/scroll, exact selection, duplicate prevention and blocked-popup handling.
- Render topology validator and Studio verification are required for the final
  snapshot. Updated stale tests to match the legitimate live popup and preservation
  baseline; no Auto Editions production code was edited by V3.

V3 production changes are limited to the new preview module, two authenticated
preview routes and the existing image viewer's pending handling. PDF, Files grid,
Orders logic, mappings, allocations, cloud generation, Photoshop/Windows companion,
Design Studio, Developer Studio, Shopify and Prodigi are unchanged relative to the
reconciled live revision. No Files desktop helper is restored.

Ready for isolated code review and non-production acceptance, **not for activating
the persistent pipeline in production yet**. Verify private bucket configuration,
secret rotation, conditional R2 operations, real staff permissions, representative
JPG/PSD limits and provider timings first. Recheck main/Render for newer concurrent
releases and test the combined revision before a separately authorised deployment.

References: [Dropbox thumbnail API](https://dropbox-sdk-python.readthedocs.io/en/latest/api/dropbox.html#dropbox.dropbox_client.Dropbox.files_get_thumbnail),
[R2 conditional S3 operations](https://developers.cloudflare.com/r2/api/s3/api/).
