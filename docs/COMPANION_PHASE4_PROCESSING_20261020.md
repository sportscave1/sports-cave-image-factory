# Companion Phase 4 — local processing and pacing

20 October 2026. **Implemented and tested locally; no Phase 4 commit, push,
deployment, migration, installed-companion replacement or startup change.**

## Ownership and actual starting point

The earlier task `20261019-2a576331`, owner `codex/companion-speed-20261020`, is
registered **Released**. Its worktree remains clean and untouched:
`C:/Dev/SportsCaveWorktrees/sports-cave-integrations-companion-phase-1-processing-and-upload-sp-20261019-2a576331`.
Its HEAD is `58569c66bf569586321da6abea0623c18691c504`, a documentation-only
follow-up to released code `e91d5d6ee2e33b57ba3cfb066b11b8125d1d40f8`.

Studio registered the isolated continuation:

- Task `20261020-06c0d1d1`; owner `codex/companion-phase4-20261020`.
- Worktree `C:/Dev/SportsCaveWorktrees/sports-cave-integrations-companion-phase-4-local-processing-and-pac-20261020-06c0d1d1`.
- Branch `codex/task/integrations-companion-phase-4-local-processing-and-pac-20261020-06c0d1d1`.
- Baseline HEAD `58569c66bf569586321da6abea0623c18691c504`.
- Registry `C:/Dev/SportsCaveWorktrees/.studio/registry.json`. Only this
  continuation's baseline/status/test evidence was changed; global approved base
  and concurrent tasks were preserved. Phase 1–3 code and retained fixtures reused.

At entry, backend and SEO worker were e91d5d6e. During the local trials a separate
task released `2859b999f88229d85e6c1c0d9d14ccd5be07e8d0`. Final read-only Render
checks show that revision live on primary `srv-d8kl4on7f7vs73dvavv0`, SEO worker
`srv-d9ujm9navr4c73amurgg` and webhooks `srv-d9146onlk1mc739nrm7g`; Render
heartbeat agrees. This task did not deploy it or incorporate its unrelated edits.

Installed companion remains e91d5d6e, main helper code hash
`8ed083cf5b3ed5a24951084425abd9075402fa12494577b9624206f8e759d253`.
Owner approved an idle-only benchmark window and normal empty Photoshop restarts.
The supervisor closed gracefully; native guard/processor lease were respected.
RAM admission initially blocked trials and was not weakened. All benchmark
documents were owned copies. Installed release was restored through its existing
supervisor/task; 392 retained journals remain unchanged. Windows venv launcher
and interpreter appear as parent/child pairs, not competing companion listeners.
Final heartbeat is Idle, no processor lock, no pending checkpoint.

Phase 1 pixel checks and Phase 2 controls are installed. Effective setting remains
owner-selected **Maximum speed**, uncapped, unpaused, one upload, acknowledged
`request_5670`; no sustainable-capacity calibration is claimed. Capability 2 is
reported. Phase 3 code/schema were released, but deployment is not acceptance:
the earlier release enabled the resumable flag before the required live
provider/native-DB/retention acceptance. A separate question about disabling that
existing flag through a configuration-only Render restart remains unanswered.
**No configuration restart or new activation was performed in Phase 4. Do not
interpret the flag as production acceptance.** Read-only session count was zero.
Required release posture remains resumable disabled until those checks pass.

## Product Uploads regression and workflow distinction

Read [the completed release report](PRODUCT_UPLOAD_COLOUR_RELEASE_20261020.md).
Its production UI evidence shows five usable automatic mockups (three lifestyle
cards are separate uploads). Final passive database check still shows upload
`06251083-2675-41c2-b379-8f8ecd1fe254`, workflow 3, **Ready**, unchanged revision
and `updated_at=2026-10-20T01:57:00.681444Z`.

Ruth source is genuinely untagged RGB8, 2835×2004, 193,732,129 bytes:

- File `id:u1tYiAa2O-AAAAAAAACGzQ`, rev `0165e3b47576fc1000000036d367e13`.
- Dropbox hash `ac5aa7d68a7265b76e22a95be0d3e684995599229d2c90c64d00f7927288e013`.
- SHA-256 `ec598df55adbb48e0b2821b430121cf87663e7e4b71ab49a457c84fef3c57d24`.
- Exact owner approval A/sRGB, group `product-upload-pinstripe-owner-20261020`;
  no Steve Smith approval, blanket assignment or original edit.

Inspection established that **current workflow 3 prepares from the PSD saved
composite on the server**, intentionally without the native companion. It would
be inaccurate to describe its existing production mockups as Photoshop renders.
Separately, the actual released companion `run_one`, with its released helper
hash asserted, rendered this same approved source through real Photoshop in an
isolated fixture queue. A controlled loopback sink accepted 3,241,227 exact bytes,
one attempt, zero retries; 5.542s fixture acceptance-to-render receipt, 0.505s
transfer, 0.456s intentional allowance wait at 50 Mbps. Source unchanged, owned
document closed, fixture jobs empty. The accepted PNG then produced all five
current WEBP-only mockups, previews and review images. No production queue,
provider upload, product creation or live recovery was performed. This proves
local native compatibility, not a new live native workflow or Cloud Ready claim.

## Retained implementation

1. `scripts/photoshop/prepare_auto_editions.jsx`: use the already-existing
   merge-full-composite/crop/restore strategy after native equivalence validation.
   Restoring a text layer now uses its captured exact layer ID, kind, top-level
   ownership and existing geometry checks. Photoshop can auto-rename text layers
   after their contents change; the earlier experimental name lookup failed
   safely on this fixture. Independent original/master/reference renders remain.
2. `scripts/prepare_auto_editions.py`: select that strategy with at least 4 GiB
   measured available RAM; retain released duplicate method below that threshold
   or when the resource probe is unavailable. No runtime restarts, purges,
   preference changes or guard bypass. Direct JSX callers still default to the
   released strategy. All existing source/proof/ICC/cleanup checks retained.
3. `scripts/render_product_upload_psd.py`: post-dispatch preservation fences use
   SHA-256 without also computing unused Dropbox digests over both complete PSDs.
   Initial immutable provider hash verification remains. Mutation on either the
   original or staged copy still fails, including dispatch failures.
4. `product_upload_artwork.py`: lossless compression level 1 for the private
   server working PNG; final encoding unchanged. Settings version becomes
   `server-psd-composite-v2-fast-lossless-png`, invalidating old derived cache.
   Original/edition exports and Photoshop PNG settings unchanged.
5. `companion_transfer.py`: bounded rate-based token bucket covers up to 32ms
   of higher-rate scheduler delay, maximum 256 KiB. Previous 16 KiB ceiling
   discarded earned credit when Windows timers woke late. Reader remains 16 KiB;
   one shared budget/slot, Mbps conversion, retry accounting, download allowance,
   control traffic, pause/reset and settings acknowledgements remain unchanged.

No preparation/upload overlap was added: measured Photoshop peak approaches
8.8 GB, Python proof work approaches 1.14 GB, retained staging approaches 870 MB
per job, and cached Photoshop actually caused RAM admission refusal. No measured
batch benefit with acceptable memory/contention/lease behaviour justified adding
that complexity. No batch throughput gain is claimed.

## Matched edition measurements

Retained Dale source: 197,770,902 bytes; SHA-256
`7ec9201b5e5601348e1017ce17127719cba8c97bcfce8c3febfbbbb3147f954c`,
file `id:u1tYiAa2O-AAAAAAAAAknw`, rev `0165da1bc6705b2000000036d367e13`.
Same own source approval, template, 4× scale, 11340×8016 output, 100 patches,
master, original, independent references 1/100 and TEST JPG. No allocations.

Three paired local runs, AB/BA/AB, fresh empty Photoshop 27.10.0 each run,
warm OS filesystem cache, verified resident source, isolated copies, no network
or competing benchmark workload. Both baseline Python and JSX pinned to Git
58569c66; candidate uses history export. All figures seconds, median (range).

| Critical-path measure | Baseline | Candidate |
|---|---:|---:|
| Source through packaged result, including Photoshop startup | 148.673 (147.324–152.153) | 119.389 (115.398–123.865) |
| Local preparation, excluding startup/packaging | 140.379 (138.368–143.728) | 112.092 (108.079–115.383) |
| Native preparation, nested inside above | 121.865 (119.921–124.797) | 93.362 (89.664–97.251) |
| Photoshop connection/startup, unchanged code | 7.630 (7.536–8.272) | 6.701 (6.698–7.869) |
| All PNG saves, nested | 42.274 (41.849–42.554) | 41.434 (40.647–42.306) |
| Patch duplication | 30.381 | 0 |
| Patch document closing | 21.188 | 0 |
| Full-composite merge | 0 | 25.047 (23.282–25.881) |
| History restore | 0 | 3.984 (3.786–4.113) |
| Packaging | 0.191 | 0.178 |

Local preparation saves **28.287s / 20.15%**. Native stage saves 28.503s /
23.39%; total including startup saves 29.284s / 19.70%. Startup variation is not
an implemented optimisation. Nested stages must not be summed with their parents.

Other stage medians baseline→candidate: source checksum 0.249→0.260s; staging
1.060→1.127s; native preflight 6.249→6.655s; document open 0.428→0.410s;
PSD inspection 0.017→0.016s; layer inspection 1.722→1.563s; layered resize
0.606→0.615s; text updates 16.108→15.075s; bounds scans 9.782→7.873s;
staged document close 0.134→0.131s; ICC preservation 0.500→0.319s;
asset hashes 0.734→0.476s; independent pixel checks 6.700→6.548s; JPG
preview 2.438→2.252s. These identify work remaining; unchanged stages' variations
are not separate attributed gains. Photoshop internal trace uses local native
durations; Python critical path uses perf_counter, with no cross-clock addition.

| Resource | Baseline median (range) | Candidate median (range) |
|---|---:|---:|
| Photoshop CPU seconds | 223.688 (217.719–226.828) | 189.875 (179.188–197.438) |
| Python CPU seconds | 16.672 (15.719–16.781) | 14.656 (14.141–15.359) |
| Sampled Photoshop peak RSS, bytes | 7,751,643,136 (7,727,349,760–7,818,653,696) | 8,517,152,768 (8,493,756,416–8,789,188,608) |
| Sampled Python peak RSS, bytes | 1,134,116,864 (max 1,135,710,208) | 1,131,520,000 (max 1,136,930,816) |
| Sampled logical staging peak, bytes | 661,266,902 | 661,273,072 |

Photoshop peak increases about **730 MiB / 9.9%**: explicit memory trade-off,
not a memory saving. Retained trial directories including packets are
870,416,115–870,423,139 bytes. Process logical I/O and whole-system disk counters
are in each raw trial; whole-system counters include other apps. Example baseline
m0b Photoshop read/write 1,925,387,717/257,043,672 bytes. System temp volume had
about 1.38 TB free. Actual Photoshop scratch-volume free space was not exposed by
the collected trace; do not substitute temp space for scratch. Preferences stayed
70% memory, 50 history states, image cache levels 4; no persistent tuning.

All three pairs pass decoded pixel/mode/dimensions/transparency comparisons for
104 PNGs, actual ICC bytes exact, all 100 edition placements, required metadata,
and byte-identical TEST JPG. Seven volatile XMP derivative identity/date fields
are allowlisted only in the diagnostic comparator. Native ICC embedding vs the
existing exact-profile repair can change valid XMP hints/repair counts; hints are
checked against the actual ICC before normalization. Wrong profile labels,
false sRGB and changed nonvolatile metadata fail. Output files are not rewritten
by this comparator; the earlier V19 comparator remains unchanged.

A second synthetic layered template verified the **normal prepare() default**,
without benchmark strategy flags: released duplicate vs automatically selected
history, all 104 PNGs/ICC/JPG equivalent. No customer template or live PSD changed.
Initial discovery's name-restore failure was cleaned up, fixed and excluded from
matched samples; retained history runs all passed.

## Product Uploads measurements

Current v3: three AB/BA/AB pairs, same immutable Ruth PSD and exact approval,
verified resident source/warm OS reads, cold derived cache every run. Actual
WEBP-only factory used; no auth/UI queue/provider timings included. Generated
destination ICC creation timestamp held identical for encoding comparison.

| Local stage | Baseline median (range), seconds | Candidate median (range), seconds |
|---|---:|---:|
| Source verification through five mockups | 3.3941 (3.3692–3.4051) | 3.3185 (3.2544–3.3366) |
| Private PNG save, nested | 0.2028 (0.2021–0.2058) | 0.0930 (0.0803–0.0976) |
| Decode including PNG save | 0.3504 | 0.2692 |
| Source hash | 0.1248 | 0.1250 |
| Preview | 0.1500 | 0.1538 |
| Cache hashes | 0.0096 | 0.0104 |
| Five core mockups | 2.7540 | 2.7593 |

Total saves **0.07565s / 2.23%**, all three candidate runs faster. Core mockups
remain the larger bottleneck; no full browser selection-to-display improvement
is established. Median CPU is 3.3125s in both cohorts. Sampled peak RSS baseline
92,704,768–108,191,744 bytes; candidate 104,796,160–114,028,544 bytes. Do not
claim a memory improvement. Private PNG grows 3,339,811→5,001,494 bytes,
**+1,661,683 bytes**; it stays server-local. All five final WEBPs, five previews
and five review PNGs are byte-identical; final WEBPs total 584,210 bytes, all 15
files 6,547,240 bytes. Cache remains eight entries / 256 MiB; count limit still
dominates for these images. Future release has a one-time derived-cache warmup.

Native/legacy path: four paired warm-Photoshop runs, AB/BA/AB/BA, including the
same five-image factory's legacy JPEG extras. Total median 6.6187→6.4442s,
baseline range 6.3039–7.5691, candidate 6.2457–6.7934. Post-dispatch verification
0.7403→0.5752s; standalone three-pair hash checks 0.4453→0.2737s. This removes
unnecessary hash CPU work without changing preservation gates; it is not the
current v3 pipeline and total variation overlaps. All native render pixels and
five mockup outputs equivalent; source ICC exact, generated web ICC timestamp
and ID differences reviewed. No fresh-start native Product Uploads speed claim.

## Pacing and transfer evidence

Three alternating pairs at each explicit fixture rate; real loopback receiver,
frozen released controller vs candidate, roughly 1.5s payload per rate (minimum
256 KiB). Some pacing runs overlapped discovery Photoshop load, which can vary
CPU scheduling; a separate focused real-receiver test also reproduces delayed
15ms wakeups. These are application payload rates, not raw wire/internet capacity.

| Cap Mbps | Released median (range) Mbps | Candidate median (range) Mbps |
|---:|---:|---:|
| 1 | 0.999 (0.999–1.003) | 0.998 (0.997–1.000) |
| 10 | 7.284 (7.263–7.453) | 9.962 (9.962–9.985) |
| 50 | 12.789 (12.582–13.205) | 49.925 (49.912–50.003) |
| 100 | 14.385 (14.366–14.451) | 99.626 (99.593–99.966) |

Receiver maximum excess over rate×elapsed was respectively 8,378 / 38,436 /
193,383 / 249,433 bytes, within allowances 12,500 / 40,000 / 200,000 / 262,144.
Short averages may use bounded starting credit. Cap is an upper bound, never a
promised speed. The trade-off is larger short bursts than the old 16 KiB ceiling;
credit is cleared on setting/pause changes. Above 100 Mbps is not measured.
At 100 Mbps, request median 10.427→1.506s, intentional allowance wait
10.148→1.351s, summed timer overshoot 8.850→1.190s, CPU 0.578→0.109s.
Peak sampled transfer RSS at most 53,460,992 bytes; control RTT worst observed
26.1ms across both cohorts, 16.4ms candidate. No busy spin, concurrency increase
or operating-system timer change. Pause, cancellation, retries, heartbeat/lease
and active cap changes are covered by the combined focused suite.

Representative complete candidate packet: **209,150,066 application bytes**, one
attempt/zero retries, 100 Mbps, 16.942s local capped transfer; CPU 0.547s, RSS
50,593,792 bytes. Disk/transport/server counters and receiver SHA match. Native
requests does not expose connection establishment: still unknown. Subsequent
independent unpack/validation 8.763s, CPU 8.297s, RSS 1,143,963,648 bytes; both
reference comparisons and outside-number proof exact. This sequential validation
is not provider publication or Cloud Ready. Provider bytes zero in these tests.

No safe package size reduction added. Transport remains version 0 under existing
compact eligibility rules: one master plus 100 patches and independent proofs.
Median packet 209,149,223→209,150,066 bytes (+843 metadata bytes, ~0.0004%).
No Phase 4 source/retry byte savings: local fixtures already resident. Existing
verified cache reuse can avoid a full identical 193,732,129-byte Ruth or
197,770,902-byte Dale download, conditional on full immutable identity/hash;
those are earlier-phase capabilities, not newly measured WAN savings. Phase 3
resume tests still pass; no live interruption/retry bytes claimed here.

No large internet benchmark, production provider transfer, or household loaded
browsing test was run. Dropbox desktop sync traffic was not attributed; system
network counters cannot identify it or prove staging is downloaded twice. No
sync selections changed. Local temp files are outside Dropbox. Historical
**288.020s remains unexplained**; no new ingress evidence attributes it. Loaded
vs idle WAN responsiveness remains an explicit authorised future measurement.

## Tests, evidence and release compatibility

Final combined focused suite: **200 passed, 1 skipped, 1 deselected**, 125.47s,
three existing dependency deprecation warnings. Covers Phase 4, Phase 2 transfers,
Phase 3 durable/restart/lost-ack/conflict/finalisation/provider recovery, colour,
mockups, native V19, Phase 1 pixels, preparation host, reliability, cancellation,
server artwork/recovery, WEBP-only and template preflight. Known baseline
`test_shopify_draft_live_completion_and_export_gate` excluded (synthetic fixture
missing edition limit). Existing stale PREPARED-vs-PREFLIGHT colour mocks were
not changed or used to weaken gates. Node V19 DOM tests, topology validation and
git diff whitespace checks and Studio infrastructure verification pass. Studio
test evidence is recorded for these local files. No broad claim that every
repository test passed.

New regression tests in `tests/test_companion_phase4.py` exercise actual receiver
behaviour with delayed scheduling, aggregate competitors/retries, pause/rate
changes and no stored surge; source/staged tampering, bounded Mbps conversion,
memory fallback, safe empty restart refusal, metadata/profile discrimination,
and raw RGB/RLE RGBA private-PNG pixel/profile/alpha preservation.
Existing `tests/test_auto_editions_native_v19.{py,cjs}` now admit the validated
strategy and check auto-renamed layer IDs, conflicting identity and cleanup.

Reusable local diagnostics added:
`scripts/benchmark_companion_phase4_native.py`,
`scripts/benchmark_companion_phase4_pacing.py`,
`scripts/benchmark_companion_phase4_product.py`.
They use isolated outputs, retained fixtures and existing guard/controller/factory
components, not a monitoring service. Additional trial drivers/raw evidence remain
ignored under `output/companion-phase4/` and `output/v19/` in this worktree.
Key records: `edition-pairs.json`, `product-pairs.json`,
`v3-png-confirmed/measurements.json`, `pacing-after/measurements.json`,
`pacing-summary.json`, `full-package-final/measurements.json`,
`final-inventory.json`, `final-tests.log`, `companion-installed-final.json`,
`photoshop-resources-final.json`, and `output/v19/queue0/companion-acceptance.json`.
An early full-packet harness assertion used the wrong outside-number proof key;
the corrected final run passed. An inventory attempt hit Windows path length;
short local temporary output fixed it. Neither was a production/runtime defect.

Generation fingerprint automatically changes from
`0d078991504d8f009c030326090df84891bfd696e3b8f59eb0f389021794c006` to
`5549059f61becba7e740d9943a7f500a0d02e717c2071b0624aea0d2fb3bdd42`.
Do not reuse old partial packets under the new fingerprint. Future authorised
release must first review/drain retained sessions, preserve their compatible
server processing, coordinate backend and companion generation modules, then
update the installed companion through its normal supervisor. Retain schema,
receipts, transfer settings and old packets during rollback; fail closed on
incompatible partial sessions. Do not silently regenerate/replay them. Current
resumable acceptance/configuration issue must be resolved before activation.

Remaining processing bottlenecks: PNG saving (~41s), full-composite merges
(~25s), number text/bounds work and independent proof checks. No final quality,
ICC, immutable mapping, edition or Cloud Ready gate was removed. Future tuning
should measure stable sustainable WAN upload plus idle/loaded request latency
once authorised, choose Balanced headroom/manual cap from that measurement,
and validate the 32ms/256KiB burst under real loaded browsing. Keep one upload;
do not infer household benefit from loopback control RTT or Maximum speed mode.
