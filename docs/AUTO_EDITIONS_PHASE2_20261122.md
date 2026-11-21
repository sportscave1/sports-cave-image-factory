# Auto Editions Phase 2 - resumable transfers and selective lossless packaging

The owner requested continuation of the diagnosed plan into Phase 2, including
its generation-bound acceptance and rollout. Keep all source, pixel, profile,
allocation and publication checks. No service or Blueprint topology changes.

## Changes

Retained packages reconcile their exact owned lease before sending any bulk
bytes. A completed receipt finishes locally without reopening Photoshop or
sending the archive again. A temporary reconciliation outage retains the packet
for bounded recovery. A legacy packet promoted to resumable transport must have
its original matching generation/checksum evidence; it is never relabelled as a
new-generation packet simply because the current client can describe it.

Selective repacking creates a separate packet in the new job folder. It never
rewrites the original or changes a durable session descriptor. It requires the
matching source, generation, archive hash, manifest, edition total and geometry;
checks pixel/profile proofs before building; then independently unpacks and
compares every reconstructed file byte-for-byte. Only a result saving at least
8 MiB and with at least 5 percent estimated sharing is selected. Existing packet
paths and partial sessions are preserved. No encoder, image dimension or pixels
are changed. Low-sharing packets skip extraction and rebuilding.

## Measurements

A controlled localhost fault/restart trial lost an acknowledgement after the
server committed 8,388,608 bytes. Client journal was still at zero. The resumed
client read the durable offset and sent only the remainder: receiver and provider
both counted exactly 16,780,221 bytes for a 16,780,221-byte fixture, not two copies.
This synthetic ZIP-preamble fault fixture is not a package-size or internet-speed
benchmark. Independent controls completed during the transfer; maximum observed
control time was 0.075 seconds in this loopback run.

A synthetic generated-image packet with byte sharing shrank from 9,518,630 to
5,844,882 bytes in 1.34 seconds including verification. It used a 64 KiB benchmark
threshold because the fixture is smaller than the production minimum; it does
not imply that a real job will save this amount. The original archive was unchanged
and all logical reconstructed files were verified.

Read-only probes of the retained Father, Son, Daytona archive found only 3,420
and 3,419 shared prefix/suffix bytes in its two roughly 54 MB references. Both
would be skipped by the current compactor. Blind repacking would waste time;
resumability and completed-receipt reconciliation are the primary gains here.

## Native acceptance and release

Preparation generation: 646e6ae37aba8e4915387939992286923b9a0f95b47828687d15131ad327951f.
Run: b284b1366cfb4acb9fe8bc409f2d0a42. Native results must be reviewed before
updating the acceptance-generation/evidence settings. The previous acceptance
was for ef4d71c7..., so its evidence cannot authorise the current generation.
The native test uses the existing installed singleton, private acceptance SQL
schema and a run-scoped Dropbox acceptance folder. Production claims are paused
only for this controlled run and must be resumed after the run-scoped endpoint
is disabled. Existing Maximum speed and transfer limits must be preserved.

The large fixture is 277,954,191 bytes, beyond the legacy 256 MiB boundary.
First interruption: server-confirmed 8 MiB; local state Awaiting companion restart.
Final native verification, cleanup, reviewed evidence hash, rollout and queue
resumption are recorded in the release evidence after completion.
