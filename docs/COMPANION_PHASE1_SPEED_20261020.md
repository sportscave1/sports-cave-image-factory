# Companion Phase 1: processing and upload efficiency

The local pixel-proof stage measured **7.323 → 5.039 seconds, 31.19% faster**,
with identical output bytes/proofs and no memory increase. This change is not
deployed. The one authorised Steve Smith recovery reached verified Cloud Ready
in **9m 24.5s** from its repaired-source queue acceptance. Its original PSD and
edition cursor were preserved. No end-to-end production speedup is claimed.

Local task `20261019-2a576331`, owner `codex/companion-speed-20261020`.
Baseline and installed companion: `dfe44257e207abe307560f21e64276990605b668`.
Code remains uncommitted and undeployed. The installed companion and startup
configuration are not changed by this phase.

## Isolation and admission

The earlier recovery worktree was on
`codex/task/integrations-recover-windows-companion-after-ssd-migrat-20261017-37907e10`,
HEAD `3be79fc2`, with five unfinished modifications. Those files were not edited.
Studio allocated a separate worktree and branch; only that newly allocated,
clean branch was aligned with the installed release. No commit, push or merge
was performed. Its registry baseline was aligned without changing the shared
approved base.

The registered companion remained running, with serving worker PID 29112.
Parent/child pythonw processes are the virtualenv launcher hierarchy; the
existing instance lock and listening session identify one serving companion.
The native benchmark guard refused a competing Photoshop benchmark even while
production was idle. No cold Photoshop launch or extra companion was started.

## Comparable local measurement

An isolated copy of the retained Dale Earnhardt Sr. — At Last PSD and its real
prepared outputs was used. Source size: 197,770,902 bytes; source revision
`0165da1bc6705b2000000036d367e13`; source Dropbox hash
`b45c8348338fd3a8f503499203cc19ab707e01bbe75c39401677ffdd801be968`.
The master canvas is 11,340 × 8,016 pixels, with 100 edition patches and native
Photoshop references for 1 and 100. No artwork was regenerated to improve the
benchmark. Every copied input/output file was hashed before and after.
There are 105 generated PNG/JPG files totalling 252,800,973 bytes. The expected
package's 105 members (including its manifest, excluding the local test JPG)
total 209,138,478 logical bytes. Staged PSDs and diagnostic sidecars are counted
separately in the raw replay inventory, not presented as uploaded assets.

The original, unchanged verification functions remain available as the
independent baseline. Three paired trials alternated execution order. Windows
file caches were not flushed; these are warm/first-observed measurements, not
cold-start figures. No production Photoshop processing ran during these trials.

| Measured local proof stage | Before, median | After, median | Change |
| --- | ---: | ---: | ---: |
| Wall time | 7.322801 s | 5.039004 s | 2.283797 s, 31.19% faster |
| Process CPU time | 7.328125 s | 5.03125 s | 2.296875 s less |
| Logical process reads, warm trial | 600,902,376 B | 400,614,920 B | 200,287,456 B fewer |
| Sampled peak process RSS | 1,126,010,880 B | 1,122,144,256 B | No increase |

The raw observations, background system network/disk counters and resource
conditions are in `output/companion-phase1/comparison-idle.json` and
`environment.json`. The system has 8 physical/16 logical CPUs and approximately
32 GiB RAM. Physical disk reads were much smaller than logical reads in these
warm trials; nearly one CPU second per wall second identifies repeated PNG
decode/comparison work, rather than saturated disk or internet, in this stage.

The final paired trials ran after recovery finished, with production idle and
no test suite running. An earlier independent paired set measured a 30.05%
reduction (`comparison-final.json`). All three final candidate trials beat
their equivalent baseline trial. These measurements do not change live code.

The first experimental batching implementation increased memory. It was
corrected to close decoded reference and difference buffers explicitly before
the next comparison, then measured again. Only the final measurements above
support the retained change.

### Implementation and correctness

`verify_preparation_pixels` scopes one decoded, content-validated master to a
single serial verification call. Each opaque number patch still has its pinned
hash, mode, geometry and ICC checked before paste. All independent Photoshop
references and the original-outside-number proof are still checked pixel for
pixel. Proof dictionaries and preparation fingerprints exactly match the
original implementation. There is no persistent cache, filename-based reuse,
cross-job reuse, altered image encoding or concurrency increase.

Only the local preparation caller uses batching. Cloud package validation,
asset publication, receipt verification, retry/resume, source checksums,
edition mappings and Cloud Ready gates remain intact. Output bytes, source
revision, template metadata and output settings are not changed by this speed
optimisation. The encoded JPG regression remains byte-identical.

This is a demonstrated improvement to the **local pixel-proof stage**, not a
measured improvement to total production job completion or upload throughput.

## Real recovery benchmark

The user separately authorised one failed design's normal recovery/uploads.
Only Steve Smith Ashes Hero Cricket Art, product
`gid://shopify/Product/8117128986931`, was selected or retried. Brock was already
Cloud Ready. Worker Health showed zero active/queued jobs and automatic backlog
recovery disabled. No pause/resume or wider backlog control was changed.

Initial source: `id:u1tYiAa2O-AAAAAAAAABHw`, revision
`0165da1c73a75b0000000036d367e13`, content hash
`33aac1a110091f22781a93b39836d676fd1e076a30788ea712435c1193b70d56`,
197,515,845 bytes. Source SHA-256:
`816ca9767e333809b776902515952cda639b403156ed897fc5e0c453c7cfbb44`.
Edition Ops identified Original Edition — ACTIVE, limit 100, next edition 66.
The preparation reference number 1 is a validation sample, not a new allocation.

### Failure and repair evidence

The prior job `b18201af318b7802c589bda8111e616eef0b3f9036ad0176`
failed with `Photoshop method unavailable`. Its earlier untagged-profile blocker
already had exact-source owner approval:
`batch-owner-appearance-20261019-8117128986931`, approval hash
`cc2c5b340eb684c37e1a469a71c1bcb21b0d8e023a4b358594d4cd49593674cb`.
No missing profile was guessed or global policy expanded.

The normal single-job Retry was accepted at 20 October 2026 10:23:48.321 AEDT.
It created job `6b8a47bcdb3fa37e42f83639e89b31aa5567b1be0f777509`.
Inspection succeeded (407 ms of native inspection), but preparation preflight
failed with `ambiguous_roles`. The PSD has visible number/plaque layer IDs
36/35 and hidden duplicate names on IDs 20/19. Native preparation correctly
refused to guess. It closed its owned document; no package/assets uploaded and
no Cloud Ready status was asserted.

An isolated recoverable PSD copy was colour-tagged with the already approved
profile, without pixel conversion. The existing processor lease protected the
idle Photoshop instance. Only visible layer 36 was renamed to
`SC_EDITION_NUMBER` and layer 35 to `SC_EDITION_PLAQUE`. Both hidden duplicates
were retained unchanged. The copy was saved and reopened; existing layer-surface
proof utilities confirmed all other text/style/effect/geometry/visibility state,
layer count, dimensions, resolution and histogram unchanged. Before/after PNG
renders were pixel-exact, and the embedded ICC matched the approved bytes.
The original source hash stayed unchanged.

The separate repaired file is 197,518,019 bytes, SHA-256
`5bf93e252b42d6b557d31370961fbc8cb166a5ddd2c08fee11bf12116eefb4b5`,
Dropbox content hash
`1db2ec1ceb6c34ee2e4ca40cd9904692cac3007237b5b74684c4e5d9595e3a1c`.
It is uploaded as a distinct filename with conflict mode Cancel, preserving
the original PSD and file ID. Mapping and completion evidence are recorded
separately after the normal workflow confirms them.
The Files UI confirmed the separate upload, then displayed both original and
recovery files. The normal picker identified new file ID
`id:u1tYiAa2O-AAAAAAAACGVg`; only this product's mapping replacement was submitted,
with both filename-mismatch and replacement audit confirmations. No edition
version was created, counter advanced or customer work generated by this task.

### Verified recovery result

Mapping was accepted at **10:34:42 AEDT**, claimed at **10:34:53**: an 11-second
queue wait. Confirmed repaired source: `id:u1tYiAa2O-AAAAAAAACGVg`, revision
`0165e39f2bf6eb2000000036d367e13`, with the repaired content hash recorded above.
Successful companion job:
`ad31714c6e59c96a5788f7da2a0e5b9df5a9345fc73de342`.

| Recovery stage | Measured time / result |
| --- | --- |
| Queue acceptance to claim | 11 s; second-precision audit timestamps |
| Host claim request | 9.940 s; overlaps claim/dispatch timeline |
| Source retrieval and validation | 15.863 s; 197,518,019 source bytes downloaded |
| Inspection including API/checkpoint fences | 16.942 s |
| Preparation and local validation, inclusive | 109.754 s |
| Native preflight, within preparation | 2.027 s |
| Photoshop preparation, within preparation | 94.399 s; 152.656 Photoshop CPU seconds |
| Document opening, within native preparation | 0.180 s; existing warm Photoshop instance |
| PNG saves, overlapping native sub-stages | 39.424 s |
| Patch duplication / close | 23.335 / 8.842 s, within native preparation |
| Local pixel proofs, within preparation | 9.048 s on unchanged live code |
| Full-quality test JPG, within preparation | 2.311 s |
| Source staging / checksum | 0.071 / 0.227 s |
| Package build / checksum | 0.470 / 0.105 s |
| Client package request through acknowledged completion | 393.197 s; 0.3800 MiB/s effective rate |
| Server body receive, within that request | 26.135 s; 156,657,382 bytes received |
| Server package/pixel/ICC validation | 14.865 s |
| Provider publication and individual hash/size/revision receipts | 47.184 s |
| Registry save / checkpoint and derived-cache scheduling | 4.532 / 3.356 s |
| Remaining technical verification | Approximately 9.104 s; calculated residual of cumulative server timers, no independent timer |
| Server request total | 105.177 s, within client request above |

Nested stages overlap; do not add these rows to fabricate a total. The
product-specific status confirmed **Cloud Ready at 10:44:06.485 AEDT**:
“Required technical checks and durable uploads verified. TEST downloads only.”
Independent wall time from successful mapping/queue acceptance to server Cloud
Ready was **564.485 s (9m 24.5s)**; durable client confirmation followed at
**573.846 s**. The entire recovery from the first failed Retry to Cloud Ready
was **1,218.164 s (20m 18.2s)**, including diagnosis, working-copy repair, its
separate upload and the successful run. The separate working-copy upload's
start was not instrumented. That whole recovery interval is not an automatic
job-performance baseline.

The successful package had **one upload attempt, zero retries**, with no
duplicate package transfer. The provider confirmed **101 new assets** (master
plus all 100 patches), **58,107,212 payload bytes**, zero reused assets for this
new source-bound preparation. Existing immutable assets were never overwritten.
Package references/original were independently validated; they are not extra
final provider assets. Generated PNG bytes totalled 205,860,105. Output remains
11,340 × 8,016 under the existing 4× settings; source remains 2,835 × 2,004 at
72 ppi. Quality, formats, ICC, transparency and enlargement settings were not
reduced. Upload byte counts are confirmed application payloads, not TLS/wire
bytes. The separate source-copy upload was another 197,518,019 confirmed bytes.

Preparation hash:
`ef7ffa08d6cdadf5ce1c83182ce5f00e5f9cb7889e24c697e1c9532155ffbe2d`.
The receipt records `Cloud assets independently verified` and completed
temporary cleanup. The original source SHA-256 was checked afterward and still
matched. Edition Ops showed **Original Edition ACTIVE, next 66, limit 100,
Cloud Ready, zero unsaved changes**. No orders/certificates were created by this
task. Completion count changed 170→171 and failed count 118→117. No other failed
design was released. Automatic recovery stays disabled. Global health retains
unrelated earlier failure indicators; this is not a wider-backlog health claim.

Sampling recorded 168.656 Photoshop CPU seconds across the observed lifecycle,
peak sampled Photoshop RSS 10,902,880,256 bytes, companion RSS 1,121,447,936 bytes.
Native generation, rather than repeated startup, is the material local cost.
Staging, checksums and packaging were small. During the 392.612-second observed
upload window, system network counters rose 172,103,521 bytes sent and
83,782,342 received. These include other applications/monitoring, not raw
per-job wire bytes. Full process I/O and system disk counters remain in the
per-second samples and `recovery-summary.json`.

Client request time exceeded instrumented server time by **288.020 s**. Current
measurements cannot divide that interval into client sending, ingress/proxy
buffering, authentication, response delay and other waits. They do not establish
an internet-only bottleneck. Upload CPU was low and the Photoshop lease free.
Future upload changes need stream/ingress timing before raising concurrency or
claiming network gains. This successful recovery demonstrates correctness, not
a speed improvement over its failed attempts or over Brock.

Raw artifacts under `output/companion-phase1/`: `recovery-summary.json`,
`recovery-audit.txt`, `repaired-recovery-observation/receipt.json`, per-second
`samples.jsonl`, native/pixel proofs, `source-repair/verified.json`,
`cloud-ready.png` and `edition-integrity.png`.

## Prior completed-job context

A read-only receipt from Brock, a different input, records 23.826 s source
retrieval, 17.156 s inspection, 123.205 s preparation/validation (105.993 s
Photoshop), 0.261 s packaging, and 402.654 s upload plus server work. Its packet
was 138,857,574 bytes with one attempt. The server reported 4.632 s receive,
16.585 s validation, 71.277 s provider publication for 101 assets/52,862,321
bytes, and 107.390 s server total.

These are historical observations, not a controlled before/after. The 0.3289
MiB/s packet-by-end-to-end-time rate includes validation/provider/database
latency; it is **not** the connection's wire upload capacity. Client and server
durations leave a substantial uninstrumented interval. Do not subtract them
and label the remainder pure network time or infer TLS retransmissions.

## Validation and limitations

- Local proof, compositor, package, colour and native guard tests: 80 passed,
  9 skipped, 3 deselected known baseline failures.
- Focused proof/preflight/host recovery tests: 47 passed.
- Encoded-JPG/identity/download correctness regressions: 8 passed.
- Three existing colour tests have stale mocked Photoshop responses: they
  return PREPARED during the required PREFLIGHT call. All three fail identically
  against the unmodified baseline caller, before the changed proof stage.
  They were not rewritten or misreported as passing.
- No cold Photoshop startup, paired native rendering comparison, external
  upload A/B, raw TLS/wire byte count or reliable internet-capacity measurement
  has been obtained. No production upload is repeated merely for comparison.
- System network counters include unrelated applications and browser traffic.
  Wi-Fi's reported 1,201 Mbps link rate is not an internet speed test.

## Files changed

- `auto_editions.py`: shared per-call pixel verification and validated patch helper.
- `scripts/prepare_auto_editions.py`: use that verifier in local preparation.
- `scripts/benchmark_companion_phase1.py`: reproducible offline real-output replay.
- `scripts/observe_companion_recovery.py`: read-only, one-product resource/stage observer.
- `scripts/repair_companion_benchmark_source.py`: guarded one-off working-copy repair/proofs.
- `tests/test_companion_phase1_pixels.py`: proof equivalence, tampering, ICC and identity regressions.
- `docs/COMPANION_PHASE1_SPEED_20261020.md`: measurements, recovery evidence and limitations.

Runtime code remains local and uncommitted on the isolated task branch. The
installed serving companion is still PID 29112 at `dfe44257`; no startup change,
companion replacement, commit, push, merge, deployment or bandwidth control was
performed in this phase. The earlier worktree still has its five unfinished
changes and was not edited. Large reproducible fixtures and raw diagnostics
remain task-local under the ignored `output/companion-phase1/` directory.

## Phase 2 recommendation

Retain one client package upload and the current bounded server publication
concurrency. Add pause/resume and shared-connection scheduling before considering
more parallel uploads. Choose a configurable upload cap only after separating
body-transfer time from provider/verification latency; the end-to-end rates
above cannot justify a reliable numeric bandwidth cap. No bandwidth control is
introduced in this phase.

## Phase 2 local continuation

Phase 2 is implemented in this same isolated task without replacing the installed
companion or repeating the Steve Smith recovery. See
[Companion Phase 2 bandwidth controls](COMPANION_PHASE2_BANDWIDTH_20261020.md)
for implementation, receiver measurements, compatibility, tests and limitations.
Phase 1's measured pixel-proof improvement and retained fixtures remain unchanged.
The 288.020-second historical interval is still unattributed; new tracing covers
the previously omitted cleanup/final-status tail but has not been deployed.
Local tests demonstrate bounded aggregate streaming and honest acknowledgement;
they do not establish improved live speed or household browsing responsiveness.
