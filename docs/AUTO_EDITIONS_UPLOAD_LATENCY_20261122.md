# Auto Editions upload latency diagnosis - 22 November 2026

Read-only investigation used retained local timing journals, onboarding/audit
records, Render metrics and deploy history. No customer data or credentials are
included. The subsequent implementation is recorded in AUTO_EDITIONS_PHASE1_20261122.md.

## Measured results

Father, Son, Daytona took 102.50 seconds in Photoshop. Local preparation and
validation took 117.77 seconds including Photoshop; those times overlap.
The generated archive was 226,910,804 bytes. Its original, master, reference 1
and reference 100 PNGs were each about 54 MB. The archive contained no PSD.

The successful transfer reached its final body handoff at 127.41 seconds and
waited another 92.45 seconds for the response. Server processing was 92.23 seconds,
including 16.29 seconds of validation, 51.83 seconds of Dropbox publishing and
8.40 seconds of technical verification. The server received 64,459,186 published
asset bytes through 101 Dropbox uploads, using the existing three-thread pool.
Do not add server totals to their component timings or infer internet capacity
from application body-handoff timings.

The retained journal recorded two complete bulk uploads: 453,821,608 bytes total.
An HTTP 503 during reconnect was incorrectly treated as permanent because the
upload handler classified requests exceptions but reconnect could raise urllib
exceptions. The product was Blocked at 08:42:15 AEDT, requeued at 08:42:41,
reclaimed at 08:49:26 and Cloud Ready at 08:55:52. That interval includes recovery
and queue work. Multiple Render rollouts overlapped; they are a plausible
contributor, not proof of the cause of every 503.

The Future Arrived likewise sent its 100,486,298-byte package twice. Photoshop
took 100.18 seconds; Dropbox publishing took 51.19 seconds over 101 uploads.
It reached Cloud Ready at 08:49:02 AEDT.

Maximum speed was active, with no recorded throttle, calibration, pause or slot
wait. Render five-minute samples showed 0.049-0.186 CPU against a 1 CPU limit,
and memory up to 1.13 GB against 2.15 GB. Brief spikes are not ruled out. No HTTP
latency samples were returned. These samples do not justify a compute upgrade
as the first fix.

## Status and handoff

Header status-read failures leave last-known popup contents visible. Both
completed products still had Waiting repair records with old preparation text
and no recorded JPG-preparation handoff hash. Cloud Ready means preparation is
ready; it does not guarantee all order JPGs have completed.

The repair worker checks one due journal per cycle and can wait 15 seconds when
idle. The observed journal set included 53 Codex queued and 38 Waiting records.
A full 90-record idle round can exceed 22 minutes before database/provider time;
this is a scheduling illustration, not a measured job ETA. Phase 1 prioritises
completed preparation before passive monitoring, using fresh authoritative
snapshots and the existing source/allocation checks.

Go Baby Go progressed to Uploading during the investigation. Other screenshot
entries included real missing/editable-number-layer and edition-range problems
and were waiting for repair, a separate wait from uploading.

## Proposed phases

1. Recovery and handoff: consistent bounded transient recovery; prioritise verified
   PSDs for eligible order JPGs; readable controls and separate transfer, validation,
   publishing, verification and JPG states; distinguish delayed status from failure.
   Gate: outage retains the verified package; 403/409 remain terminal; completed
   preparation wins over passive backlog; no fabricated JPG completion.
2. Avoid repeated bytes: complete generation-bound acceptance of the existing
   resumable provider/Postgres/retention path. Benchmark lossless compact reference
   packaging and safe repacking of reusable legacy archives. Do not enable an
   unaccepted protocol flag. Gate: interrupted body/response/deploy resumes
   acknowledged bytes without reopening Photoshop or changing pixels/profile.
3. Reduce publishing overhead: benchmark bounded batching/concurrency and exact
   immutable receipt reuse against the 101-upload, 52-second baseline. Gate: measured
   improvement, bounded RAM/requests, 429 backoff and safe partial retries; no skipped
   validation or overwritten assets.
4. Controlled overlap: consider one prepared upload alongside the next Photoshop
   job with strict RAM/disk quotas and the existing Photoshop singleton. Isolate
   lightweight status reads from imports and consolidate deployments during bulk
   work. Gate: higher completed jobs/hour plus safe pause/cancel/restart, accurate
   identity and measured status freshness/p95.

Phase 1 changes were developed on synthetic fixtures. Production release and
local companion installation are tracked separately; later phases are not enabled.
