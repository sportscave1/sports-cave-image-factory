# Companion Phase 3: durable package resume

Implemented locally for review. No commit, push, deployment, production migration,
companion replacement, startup change, Photoshop run or live recovery occurred.
All Phase 1/2 changes remain. The installed companion is unchanged.

## Workspace and baseline

- Task `20261019-2a576331`; owner `codex/companion-speed-20261020`.
- Worktree `C:\Dev\SportsCaveWorktrees\sports-cave-integrations-companion-phase-1-processing-and-upload-sp-20261019-2a576331`.
- Branch `codex/task/integrations-companion-phase-1-processing-and-upload-sp-20261019-2a576331`.
- Git HEAD `dfe44257e207abe307560f21e64276990605b668`, still uncommitted.
- Git/Studio identity checked before editing and after testing. Existing working
  changes were preserved. The SSD recovery worktree still has its original five
  modified files; it was not edited.
- Installed PID 29112 still serves approved `dfe44257...`, task
  `20261012-54a08610`; host status remains Companion Connected. No competing
  companion was started. Test receivers use isolated ports and synthetic hosts.

Read alongside [Phase 1](COMPANION_PHASE1_SPEED_20261020.md) and
[Phase 2](COMPANION_PHASE2_BANDWIDTH_20261020.md). Steve Smith was not replayed.
The historical **288.020-second interval remains unexplained**. Loopback does
not observe production proxies, ingress or browsing; no live speed/interference
improvement is claimed.

## Package audit

The retained Dale packet still has one master plus 100 edition patches.

| Content | Members | Application bytes before ZIP overhead |
|---|---:|---:|
| Final master and patches | 101 | 58,994,113 |
| Original and independent references 1/100 | 3 | 150,103,985 |
| Manifest and source/colour metadata | 1 | 40,380 |
| Complete ZIP, including overhead | 105 | **209,149,198** |

There are **no exact duplicate members by SHA-256**. Each reference shares only
a 3,409-byte prefix and 12-byte suffix with the original. They fail the unchanged
compact rules (middle at most 1 MiB and shared spans at least 64 KiB). Dale stays
transport version **0**. Eligible compact transport version 1 remains available;
upload protocol 1 is a separate version and does not alter the package format.
References, original/outside-number proofs, ICC checks and receipts remain.
No remote reference or trusted client substitute was introduced.

Offline compression results, with every decompressed member hash checked:

| Format | Bytes | Saving | Packaging time |
|---|---:|---:|---:|
| Existing stored ZIP | 209,149,198 | 0 | 0.173 s |
| Deflate 1 | 219,868,967 | **10,719,769 more** | 2.457 s |
| Deflate 6 | 208,911,331 | 237,867 (0.114%) | 5.528 s |

Neither change was retained: level 1 enlarged the packet; level 6 added about
5.35 seconds for negligible saving. Encoding, dimensions, resolution, profiles
and quality did not change. All retained fixture/source hashes are unchanged.

## Implemented byte avoidance

- New bounded **512 MiB LocalAppData source cache**: exact provider ID, immutable
  revision, size, Dropbox content hash and local SHA-256; rehash before and after
  staging. Existing grant/mapping checks still bind product/run. Verified render
  and source-preparation copies populate it. No browser path guessing, moving
  originals or Dropbox desktop setting changes. The authorised native manifest
  can also use the existing non-hydrating, hash-checked resident synced path.
- Protocol-1 output/package reuse requires source/run/output settings plus
  preparation hash, actual packet SHA and generation fingerprint covering
  template, Photoshop scripts and relevant Python generation/colour code.
  A partial session requires its retained packet. Missing packet/provenance or
  changed generation fails closed rather than regenerating or replaying it.
- Resume queries server-confirmed progress. Accepted chunks and an already
  completed packet are not uploaded again. Completed job receipts still apply.
- Existing immutable final-asset publication reuses independently checked
  size/hash receipts, complete listings and per-file fallback. Its concurrency
  stays at three; no filename/existence-only skip was added.

Caching the real 197,770,902-byte source took **0.638 s**; verified reuse took
**0.602 s** and conditionally avoids that many download bytes. This is byte
avoidance, not measured live download acceleration. It adds hashing/local copies.
New client cache files are outside sync folders; existing job folders/originals
were not relocated. Server durable ZIPs use the existing Dropbox Cache area.
Desktop sync of that area, if selected, is outside the controller and remains a
release consideration. No claim covers desktop sync or other household devices.

## Durable upload protocol

The new `companion_package_*` modules reuse the existing authenticated web app,
PostgreSQL connection, Dropbox upload sessions, background worker and importer.
No separate upload service is created. Migration
`supabase/migrations/20261020002955_companion_resumable_packages.sql` was prepared
through the existing Supabase CLI workflow and executed **only on disposable
PGlite PostgreSQL**. RLS and privilege tests deny browser roles table access.

Sessions bind authorised actor, host hash, application/shop origin, exact
product/edition-run context and lease, immutable source, manifest/preparation
hash, generation fingerprint, size, full SHA, per-chunk SHA and protocol version.
Create requires the existing exact host-owned preparation grant. Every operation
rechecks host, account, current mapping/source and lease, or the exact completed
receipt. Expired/superseded authorisation is not resurrected. Provider session
IDs, grants and tokens never appear in progress or client journals.

Create/recover, status, chunk and finalise use existing authenticated host routes.
Chunks are **8 MiB**, final chunk shorter, with explicit aligned positions and
integrity checks. Each streams through the Phase 2 single slot/shared allowance
and 16 KiB reader: Dale needs **25 chunk requests**, not thousands. Server memory
holds at most one bounded chunk. It validates bytes/SHA, appends to the durable
provider session and commits SQL offset/hash state **before acknowledging**.
Identical repeats are safe; conflicting bytes, positions and identities fail.

Lost provider append acknowledgements recover through exact next-offset results;
server-computed complete Dropbox hash and complete package SHA still gate import.
Finish checks the deterministic staging object's exact ID/revision/size/hash.
The receipt and `Queued` state commit in the same row/transaction: **the session
row is also the durable processing job**, avoiding a receipt/enqueue crash gap.
The optional wake follows commit; the existing 15-second worker also discovers
queued rows after restart.

The worker claims with `FOR UPDATE SKIP LOCKED`, downloads the pinned durable ZIP,
checks full SHA and calls the shared legacy importer. It holds the row transaction
during processing, with a 10-minute idle transaction fence. Crash rollback leaves
Queued recoverable; bounded transient retries retain verified publication work.
An exact completed checkpoint avoids repeated download/publication. All package,
ICC, hash, pixel, reset, mapping, technical/visual and Cloud Ready gates remain.
Session `Complete` means import finished; only actual existing verification may
report **Cloud Ready**. Pending technical/human review stays distinct, with the
existing queue health providing authoritative later status.

Sessions expire after six days, before the provider's seven-day limit. Cleanup
locks at most two expired rows per pass, checks the exact receipt and recoverably
deletes only its own hashed staging ZIP. It handles provider finish committed
before SQL receipt recording. Small tombstones prevent same-ID resurrection.
Uncommitted provider sessions expire at the provider. Originals/final assets
are not cleanup targets. Retention bounds age, not total shop-wide storage;
capacity and long outage behaviour require release acceptance.

Provider contracts: [session lifetime](https://docs.dropboxapi.com/dropbox-api/api-reference/user-endpoints/files/upload-session-start),
[offset recovery](https://opensource.dropbox.com/SwiftyDropbox/api-docs/latest/Classes/Files/UploadSessionAppendError.html).

## Pause, progress and compatibility

Capability **2** adds pause at a safe confirmed chunk boundary. Resume uses the
same session/job/packet and queries position/authorisation again. Legacy/render
transfers keep “Pause after current transfer”. This does not pause the whole
worker or enable backlog recovery. Independent heartbeats, lease renewal,
cancellation and settings remain responsive. Verification-only recovery sends
no bulk bytes and works while paused or awaiting calibration.

Worker Health retains modes, local persistence, correct Mbps conversion, ordered
requested/effective acknowledgements, download allowance and calibration guards.
States distinguish Uploading, Paused/Resuming, Uploaded, verifying and Cloud Ready.
Resumed offset, disk bytes, transport handoff and confirmed server bytes remain
separate. Transfer-only speed/ETA excludes pause/chunk-ACK/provider/verification
wait; verification has no transfer ETA. These are application counters, not wire
throughput. Unsupported/offline companions do not falsely acknowledge settings.

Session correlation extends existing diagnostics. Per-chunk monotonic handler,
body-receive and durable-provider/SQL durations accompany client response waits.
Staging download and complete SHA have separate durations. Last-three request
details and cumulative bytes/request totals survive restart. Telemetry is bounded
and excludes credentials, signed URLs and bodies. Unexposed connection/proxy time
remains unknown; no clocks across processes are subtracted.

The original legacy endpoint and limiter remain available. Protocol 1 is offered
only with the explicit resumable flag and existing durable worker enabled.
A retained new session never silently falls back to a full legacy upload.
Other source/native/render paths retain Phase 2 rate control and legacy transfer
semantics; this phase does not promise their mid-file resume or browser control.

## Evidence and trade-offs

Retained evidence: `output/companion-phase3/measurements.json`,
`recovery-measurements.json`, desktop/mobile screenshots and
`scripts/benchmark_companion_phase3.py`. Synthetic auth, local fsynced provider,
disposable SQL, loopback and explicit fixture rates; **no internet calibration**.

| Measurement | Result |
|---|---|
| Required real package bytes before/after | 209,149,198 / 209,149,198 |
| Legacy streaming/hash sink, median of 3 | 0.852 s |
| Durable protocol/mock-provider completion, median of 3 | 3.708 s |
| Additional measured component cost | +2.856 s (+335% of simple sink) |
| Full real independent validation | 9.497 s; 105 exact members, 3 passing proofs |
| Completed packet recovered without local journal | 0.280 s; **0 package bytes** |
| Fault fixture (ZIP preamble, not size evidence) | 16,780,221 B |
| Injected lost chunk ACK | One HTTP 503 after 8,388,608 B accepted; local offset 0 |
| Receiver and companion/controller recreated | Only remaining 8,391,613 B sent |
| Total received/appended across both attempts | **16,780,221 B; no accepted chunk resent** |
| Controls during resumed capped transfer | 45; worst 0.04694 s |

The normal comparison measures component cost, **not** end-to-end backend
before/after speed: legacy sink streams/hashes; new path additionally journals,
fsyncs staging, verifies receipt, fetches staging and rehashes. Full validation is
measured separately, not added across overlapping stages. No normal successful
speed improvement is claimed. Durable staging adds server-to-provider packet
upload and provider-to-server fetch before unchanged final publication. Remote
latency/egress and real fresh auth/source checks are unmeasured. This is an
explicit reliability/storage/latency trade-off, disabled by default, requiring
authorised live acceptance.

Peak sampled process RSS: simple sink **71–77 MB**, durable trials **86–93 MB**;
large independent validation **1,163,628,544 B**. One durable ZIP uses 209,149,198 B;
processing temporarily adds that ZIP plus 209,138,478 B expanded members locally.
Three mock trials retained 627,447,594 B provider staging until cleanup. Cache
budget is 512 MiB. Sampling excludes separate PGlite Node memory and can miss
short peaks. System counters include unrelated processes and are not wire
measurements. Reads were warm/first-observed, not forced cold; concurrent machine
activity adds noise. Phase 2's 8.529 s validation vs this 9.497 s is not a matched
processing comparison and establishes no gain/regression.

At a 32 Mbps upper cap, resumed body handoff took **4.834 s**, including **4.738 s**
allowance waits; verification took **0.099 s**. The cap is an upper bound, not
guaranteed throughput: Windows wait scheduling and the retained small burst
bucket can underfill high caps. Phase 2 burst/concurrency limits were not enlarged.
The pause test confirms zero new bytes while paused at a boundary and a control
request under 0.5 s. Existing receiver-side aggregate/burst/rate-change/retry and
persistence tests still pass. Household responsiveness remains unmeasured.

A complete acknowledged chunk is not resent after lost ACK, as measured. An
incomplete/unaccepted chunk may require up to 8 MiB resent; mid-chunk continuation
is unsupported. Finalisation repeats do not duplicate publication. One injected
HTTP failure and two client attempts are distinct from package retransmission.

## Tests

- Expanded Phase 1/2/recovery/native/reset/cancellation suite: **235 passed,
  1 deselected, 2 subtests passed**.
- New protocol suite: **18 passed** after final changes. Includes actual immutable
  publisher recovery with provider mocks: two verified assets reused, one missing
  asset uploaded, no duplicate writes. Its initial mock omitted provider paths;
  existing verification correctly rejected it. The fixture was fixed, not the gate.
- Final combined protocol/package/controller/health/host regression: **127 passed**;
  additional fingerprint/negotiation/retry selection: **3 passed**. The timing-header
  parser was hardened to ignore non-string diagnostic headers after a legacy retry
  mock exposed that edge. Syntax, changed-file secret checks, Studio unit tests
  and `git diff --check` pass; results recorded with Studio.
- Phase 3 and retained Phase 2 browser tests pass at **1280/390 px**: capability,
  calibration, requested/effective/stale ACKs, progress and honest verification ETA.
- Fault coverage: success/finalise; lost client/provider ACK; duplicates/conflicts;
  server adapter/client recreation; transaction-crash rollback; repeated finalise;
  partial publication and completed checkpoint recovery; source/generation/packet
  changes; expiry/cleanup; RLS/auth rejection; pause/control/budget; legacy route;
  corrupt/incomplete packages never Cloud Ready.
- PGlite fixture serializes transactions through one connection. Concurrent calls
  test repeated/idempotent outcomes, **not native multi-process PostgreSQL races**.
  Restart uses recreated server/provider/client objects and persistent fixture
  data; crash tests inject rollback, not production process termination.
- Actual Dropbox/Render ingress, native DB contention, long-duration 6/7-day
  retention and real browsing require authorised live verification.
- Known unrelated baseline exclusion:
  `test_shopify_draft_live_completion_and_export_gate` lacks the synthetic
  product's verified edition limit, previously reproduced against HEAD. Earlier
  three stale colour-mock preflight expectations remain documented in Phase 2.

## Files and release requirements

New: `companion_atomic.py`, `companion_source_cache.py`,
`companion_package_identity.py`, `companion_package_store.py`,
`companion_package_provider.py`, `companion_package_api.py`,
`companion_package_client.py`, private migration, Phase 3 benchmark/tests/UI test
and report. Extended: `companion_transfer.py`, `companion_transfer_control.py`,
`scripts/studio/auto_editions_local.py`,
`scripts/studio/product_upload_render_local.py`, `auto_editions_onboarding_api.py`,
`auto_editions_setup_api.py` (shared importer), `auto_editions_runtime.py`,
`files_upload_api.py`, `worker_health.py`, `components/worker_health/index.html`.
`tests/test_auto_editions_reliability.py` updates its expected protocol argument.
Earlier Phase 1/2 and unrelated changes remain. No generation/template or
provider-publication-concurrency change was introduced.

Required rollout, **not executed**:

1. Review/apply private migration through normal workflow; release backend first,
   including new modules, routes, worker and capability-2 health validation.
2. Keep resumable off until provider permissions, native DB race/retention and
   storage capacity acceptance pass. Enable
   `COMPANION_RESUMABLE_UPLOADS_ENABLED=true` only alongside existing
   `SPORTS_CAVE_AUTO_EDITIONS_V6=true`.
3. Release matching companion/generation modules after backend acceptance.
   Fingerprints must agree; drain/review retained sessions before generation
   changes. Retain persisted settings and partial packets.
4. Obtain fresh authority for controlled live transfer/receipt/ingress/browsing
   acceptance. Never reuse Steve Smith's completed authority or release backlog.

Rollback retains schema/data and protocol-1 processing until accepted sessions
drain. Old clients continue legacy work on the new backend. Flag-off/old backend
makes new partial clients fail closed, not replay. Do not remove table/staging/
local packet while needed. Installed/live state remains unchanged now.

Phase 4 should measure Photoshop cold/warm startup, document open and exports
with isolated copies and exact quality checks, then address the measured
processing bottleneck. Retain ingress attribution, native DB contention,
provider staging latency/capacity and high-cap Windows scheduling as explicit
acceptance/follow-up work. Do not weaken source, ICC, pixel or mapping gates.
