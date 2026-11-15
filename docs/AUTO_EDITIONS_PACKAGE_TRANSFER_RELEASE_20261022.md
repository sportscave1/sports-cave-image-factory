# Auto Editions package transfer release — 22 October 2026

This follows [the failure investigation](AUTO_EDITIONS_PACKAGE_TRANSFER_20261022.md).
The owner explicitly authorized commit, push, deployment, Companion update,
required resumable acceptance configuration and normal retry of Tempted.

## Deployed release

- Feature commit: `c3d9f1d8`; released merge:
  `b78b78356cbc891dfd8b94aaec21d3082cad5642`.
- Existing primary `sports-cave-os` (`srv-d8kl4on7f7vs73dvavv0`): final activation
  deploy `dep-dbcnfcjncjis73d1o87g`, live 02:43:29 UTC.
- Existing worker: `dep-dbcmtbe1egvs73etoic0`; existing webhooks:
  `dep-dbcmtbe1egvs73etoir0`, both on the same release.
- Companion immutable release `approved-b78b78356cbc891dfd8b94aaec21d3082cad5642`.
  The existing startup task's action was updated; identity, triggers and settings
  were retained. Pairing, source data and transfer preferences were preserved.
- No service, Blueprint, infrastructure size, image policy, unrelated workflow
  or production-readiness setting changed. Topology validation passed.

Only the primary's required acceptance keys changed: resumable uploads enabled,
scope `provider-postgres-retention-large-v2`, generation
`4b7c8bb87398acb1e38e53b14c4728bf8754b904e18c17fa64cc47f789c95c96`, reviewed evidence
SHA-256 `4187ace54e1511dd9c5ad0ba53bb60548cd690e7b960b390404b645ef1baf7d6`.
The temporary isolated acceptance run was cleared after completion; its endpoint
then returned HTTP 409, "Isolated acceptance is disabled."

## Acceptance before activation

The merged release passed 129 focused local tests, including PGlite, loopback
HTTP, actual boundary files, legacy compatibility, corruption, retry/restart,
authorization, proofs and lossless transport. Actual Tempted exports also passed
local transfer/restart/import verification with all 105 reconstructed files
identical. These are local results, distinct from the live results below.

Live isolated run `fc0bf0f7721f45288c9a0616fb4e1a2c` used real native PostgreSQL and
Dropbox, a bounded 277,953,983-byte synthetic package and its isolated schema.
The large ZIP preamble tests transport load; it does not measure artwork
compression or quality. No customer allocation/job was used for acceptance.

- Concurrent creates returned one session. Lost first chunk acknowledgement,
  normal Companion restart and lost finalize acknowledgement all resumed that
  same session without repeating accepted bytes or the completed body.
- A further HTTP interruption preserved the 75,497,472-byte confirmed offset.
  The harness did not record its HTTP status; no network cause is inferred.
  Resumption of the same session completed successfully.
- A deliberate retryable interruption after master publication reused its
  exact provider file ID/revision. All 101 assets were independently downloaded
  and verified, with three image proofs, before isolated Cloud Ready.
- Expired test-session retention cleanup succeeded while the active main
  acceptance package remained intact. Completed receipt recognition passed.
- Owner settings remained Balanced, sustainable 3.8 Mbps, effective 2.85 Mbps.
  Real loaded control probes were approximately 2.1–2.4 seconds, similar to idle
  WAN requests. No claim of sub-500 ms WAN control latency is made.
- Observed acceptance ingress memory was at most 758,243,300 bytes against the
  unchanged 2,147,483,600-byte service limit. The actual image verification result
  must additionally be checked below.

The reviewed report and immutable evidence are retained in the task runtime
directory, with the SHA above used for activation.

## Normal Tempted recovery

Normal UI Retry was accepted at 02:48:06 UTC. The existing host claimed it at
02:48:44 UTC. New local job `e7d0b3b1468b251b00880d4a8e843ac96aca3d2c70445727`
negotiated protocol 1 and a 1,073,741,824-byte budget. It reused the verified
exports from the original failed job, without rerunning Photoshop or changing
that job's PSD/journal. Its package is exactly **292,429,952 bytes**, SHA-256
`021a8b8ae51718a7c73e12c309a337a9bef61bebcbaefc85694a49d6993b0de1`.
Preparation identity remains
`36f0d1f9569ec87b74c15c84b38ba6b61d5da9113128943907992409f339616c`.

Public durable session:
`77fb3bd89ba926852cd5ce0a0777a81e83ff6a85dcd42aed8d84c6f24928c6db`.

All **292,429,952 bytes** were accepted in **35 body requests**, largest
8,388,608 bytes, with exactly one durable session. Actual client accounting
recorded the same total payload bytes, with zero resumed bytes and no repeated
body. Finalization queued the package at 03:13:26 UTC. The import independently
checked its complete SHA-256, validated the images in 24.611 seconds and
published **101 unique assets** totalling **101,941,792 bytes**. The two edition
pixel proofs and original-outside-number proof passed. All 105 logical package
files were additionally compared with the retained failed exports byte for byte.
No image was resized, re-encoded or regenerated during this recovery.

The first technical commit encountered PostgreSQL `DeadlockDetected` at
03:15:21 UTC while updating onboarding, after image verification. Its existing
bounded retry retained the imported preparation; the second attempt downloaded
and checked the immutable cloud assets and succeeded at **03:18:21.218942 UTC**.
Authoritative onboarding is **Cloud Ready**, technical check **Succeeded**,
current exact-hash layout certificate `technical_verified=true, test_only=true`.
The live UI independently showed Tempted — Conquering Everest Wall Art —
Cloud Ready, Companion Connected, no active preparation.

The completed upload receipt correctly retains its earlier `Uploading` response
snapshot, and the local job says `Prepared` / `Uploaded, verifying`; the later
authoritative technical/onboarding result and live UI establish final readiness.
No success was inferred from those earlier snapshots. The fresh job's temporary
ZIP remains retained because its initial response did not authorize cleanup.

**Production readiness remains required.** This is the existing technical TEST
readiness flow. `print_ready=false`; no visual approval, supplier certification,
physical target/bleed verification or production readiness was fabricated.

Final preservation comparison matched the pre-retry baseline exactly: original
PSD SHA-256 `9eeaad3f82d52e9ecc7d8c7e47936d3427daf593132bfe6498f16ee1cda25847`,
same mapping and timestamp, one edition run
`92392952-9fcd-477b-8308-145632665820`, total/remaining 100, next edition 1,
last assigned 0 and sold count 0. No duplicate session, asset name, job submission
or edition allocation was created. Original failed job and completed work remain.

Peter Brock, the previous successful new design, still has its original
`61b7ad1fdc1f2e2055f2e3eded533177669314fcf967ae07e79b5c249a7c8167`
preparation, Cloud Ready status and one attempt. Its historical 138,857,574-byte
packet fit the old cap; the same approved dimensions and policy generated much
smaller PNGs for that artwork. Its cleaned-up historical original/reference files
were unavailable for a new byte comparison; the investigation records the
retained receipts and that limitation. Legacy/successful package behavior was
also covered by the focused release tests.

The highest available 60-second Render memory sample during actual recovery was
568,262,660 bytes against the unchanged 2,147,483,600-byte limit. These sampled
metrics are not a measurement of instantaneous peak; the actual full-size local
process peak and bounded-buffer/disk tests are recorded in the investigation.
The production import and later independent technical retry both completed.

Runtime evidence includes `actual-recovery-result.json`,
`live-preparation-receipts.json`, `live-packet-byte-verification.json`,
`actual-recovery-memory-samples.json`, original preservation baseline,
Companion startup XML comparison, reviewed acceptance report and
`tempted-cloud-ready.png`. No credentials are included in this report.
