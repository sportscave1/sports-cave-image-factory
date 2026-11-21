# Phase 4: controlled preparation/upload overlap and responsive progress reads

Requested release: finish Phase 4 and push the combined updates to Git/Render.
Studio task 20261121-d23adb8e, owner codex/editions-phase4-20261122. The primary
service remains sports-cave-os / srv-d8kl4on7f7vs73dvavv0. No Blueprint change.

## Behaviour

The existing processor lease still allows exactly one native Photoshop operation.
Once a validated package is built, checksummed and its native lease released, one
automatic preparation may overlap its resumable upload. No third job is admitted.
The existing shared upload controller still permits one package transfer, with
the existing speed settings, cap, pause and durable offset handling. A second
finished package waits for that slot; it cannot start another simultaneous upload.
Interactive and legacy preparation remain serial.

Before an overlap claim, the local worker requires 4 GiB available RAM, 12 GiB
free staging space, no native processor lock, no cancellation/recovery/checkpoint
backlog, and an owned bounded workspace. The 8 GiB active-workspace admission cap
reserves 2 GiB for the next maximum-sized source before downloading it. Before
native work begins, it rechecks RAM, 8 GiB remaining free disk and estimated
workspace growth (two more source-sized copies plus 2 GiB). If this no longer
fits, the second job waits cancellably for its uploading peer to finish and then
uses the existing serial checks. Unknown counters or unexpected links fail
closed. Source-size, package, pixel and colour guards are unchanged.

The server independently checks the claimed lease's actor, exact registered host
hash, current unexpired product lease, cancellation state and an acknowledged
Receiving/Queued durable upload. An unacknowledged session cannot exclude an
active preparation. One existing preparing row can be excluded from a new claim;
any second active row blocks another claim under the same table lock. Global
Pause is checked before admission. Both active jobs receive their own heartbeat,
source fences and cancellation handling. A restart restores owned journals through
the existing serial recovery path; it does not steal a processor lock.

Pending upload-status reads authenticate the current registered host and exact
session, check origin/expiry and validate descriptor/generation, then return only
durable pending progress. They avoid mapping/provider revalidation and a redundant
session SQL read. Every write and completed-status response retains the existing
fresh source/lease/mapping checks. A pending result can never claim Cloud Ready.

Accepted packages are now drained before optional repair/provider diagnosis in
the existing worker loop. Pipeline claims also skip optional colour-recovery scans;
the newly selected source still gets its normal authoritative colour and identity
checks. Live-session lookups get a partial index, excluding completed history.

## Evidence

Three warmed 12-job scheduler replays used the actual local start admission and
processor lease, with synthetic 40 ms native work / 80 ms transfer work. Median
elapsed time was 1.645 s serial and 1.022 s overlapped: 37.9% less elapsed time,
with maximum native and upload concurrency both one. Source/receipt identities
were unique across all jobs. These artificial rates are not production jobs/hour
or a Photoshop/provider throughput promise. Reproduce with
scripts/benchmark_editions_pipeline.py; raw results are retained in this task's
.studio/runtime/pipeline-replay.json outside Git.

A real local HTTP receiver with disposable SQL handled ten pending-status reads
while a write-side fresh-source fence was deliberately delayed 400 ms. Observed
sample p95 (nearest-rank, ten samples) was 5.15 ms. This measures fixture HTTP
responsiveness, not production network p95. Completed-status source changes still
return 409. Real queue tests cover two live leases, rejection of a third claim,
pause, expired/zero acknowledgements, superseded leases and cross-host/actor
denial. The actual start/prepare worker tests overlap a held first upload with a
second native lease; cancelling the second retains its source and leaves the first
upload intact. Existing durable HTTP restart/retry and pixel/profile tests are
included in the focused release suite.

Two legacy test expectations were aligned with already released behaviour:
direct JPG links use #Open JPG and inline=1, and review status displays Repair.
Their original source-change, cancellation, allocation and no-provider-scan
assertions are retained. No production behaviour was changed for those fixtures.

The first observed production Phase 3 import completed with zero retry attempts,
53.191 s Dropbox publishing and 110 direct provider calls (including chunk calls).
It finished its durable import with Uploading/technical verification still pending;
this is not evidence that every order JPG is complete. Different artwork/package
sizes prevent a controlled speed comparison with the original 52 s baseline.

## Release

The existing service and installed local Companion require separate updates.
Pause new claims at the safe boundary; finish the current upload; install only a
tested immutable release; preserve the existing scheduled task owner, transfer
settings and source journals; then resume. Do not force-kill Photoshop, an upload,
or an external repair process. Keep preparation generation and resumable evidence
unchanged because the native generation contract files are unchanged.

Final test count, migration/index verification, deployed and installed revisions,
queue resumption and native observations belong in this task's release evidence.
No UI or pipeline performance number is a zero-error guarantee. Phase 4 does not
increase upload concurrency or reduce artwork validation.
