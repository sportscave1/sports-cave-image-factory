# SC3340 local native comparison and coordinated release

21 October 2026. Original task `20261020-04713977`, owner
`codex-print-info-20261021-01a15bad`, branch and all uncommitted files retained.
Integration is isolated in Studio task `20261021-c9996ddd`, owner
`codex-sc3340-release-20261021-01a15bad`, branch
`codex/task/release-sc3340-fractional-preparation-release-comp-20261021-c9996ddd`.
The release task fast-forwarded its approved starting base to existing Git main
`9991df9ad3f6cece5d1d7a7a52e556db2feebd53`, then explicitly combined the tested
resolution-information and fractional-sizing changes. Current released Files,
source-role recovery, alpha preflight, ICC and preparation strategy code is retained.
Two merge conflicts were resolved to preserve the current preflight/transfer flow
and add the target check to shared import_archive (both upload transports).

## Native safety and result

Initial available RAM was 9.015 GiB, subsequently 8.68 GiB after the idle companion
stop; 4 GiB benchmark admission and existing processor lease were respected.
Screen task doer processes 29104 and 33012 (`task_recorder.server`, independent
TaskRecorderHelper installation) were not stopped, restarted or updated. PID 9468
was a separate Studio companion worker hosting Auto Editions. Its authenticated
supported stop operation returned stopped=true after its own idle checks. No process
was killed. No unfinished/checkpoint-pending local preparation journals or resumable
upload-session files were found. Prepared/blocked historical journals remain intact.
Photoshop initially was closed. Only the empty benchmark-launched Photoshop was
normally closed between trials and after completion; no user document was closed.
Screen process creation timestamps matched before/after the complete native run.

Pinned source Dropbox content hash:
`7cb591993ce4c738db007f86b06f93027e1933ea3e269e124f20d8a1e43d3346`.
PSD SHA-256 before and after:
`fe816181fc35f49de30952ee431a22a18808249ad176b8109d4655180185fec9`.
No source PSD was saved, mapping or allocation changed, cloud asset published,
archived output replaced, live order modified, or supplier submission made.

| Property | Archived SC3340 edition 059 | New local edition 059 |
|---|---|---|
| Pixels | 7016 × 4961 | 9933 × 7024 |
| Canvas scaling | 1× | 1.415763968073× by width, proportional rounded height |
| Pixel count | 34,806,376 | 69,769,392, within unchanged 95 MP budget |
| A1 PPI, 841 × 594 mm | 211.8982 × 212.1370 | 299.9979 × 300.3529 |
| Native-source PPI | 211.8982 × 212.1370 | 211.8982 × 212.1370 |
| JPEG bytes | 15,555,990 | 26,325,647 |
| Profile | RGB, embedded 3144-byte sRGB ICC | Exact same ICC bytes |
| Encoding | JPEG quality 100, 4:4:4, 300 × 300 DPI metadata | Unchanged |
| Status | TEST / NOT PRINT READY | TEST / NOT PRINT READY |

ICC SHA-256:
`2b3aa1645779a9e634744faf9b01e9102b0c9b88fd6deced7934df86b949af7e`.
Archived JPEG remains SHA-256
`b255bdcf1e0f9309d1b92a9b839a1a0cf465eb76f18ff874eea4180eb0655c42`.
Revised JPEG SHA-256:
`9be3c6189db7bbc097a521735115122561afc5bd972147877706c7caa03b50d5`.
The new manifest/preparation fingerprint is
`c11f6da7f159ebebc92d37c783b1414595e3ee3ba1ccd9c5d2a1ab89a0a22709`.
Its full geometry plan participates in prepared master and future job identity.
Old archives/fulfilled outputs are not invalidated or regenerated.

Final measured preparation wall time: 125.255 s (includes native startup/preflight,
exports, hashes, pixel verification and local JPEG). Native export phase 90.670 s,
preflight 19.555 s, actual layered resize 0.696 s, pixel proofs 5.386 s and local
JPEG 1.590 s. At ~100 ms sampling, Photoshop peak RSS was 8,911,220,736 bytes
(8.30 GiB); Python peak RSS 1,886,121,984 bytes (1.76 GiB). These are separate
per-process peaks, not a measured simultaneous total. Sample count 1119. Logical
temporary files peaked at 1,624,873,109 bytes; this is not Photoshop scratch usage.
The original archived export has no matched new baseline RSS measurement. Historical
receipt timings are not a controlled runtime comparison. No speedup is claimed.
Larger preparation increases memory/filesize; 95 MP alone is not a RAM guarantee.
No worker limit, resampler, sharpening, colour conversion or encoder setting changed.

100 patches were produced. Independent reference comparisons for editions 1, 59
and 100 passed pixel-exactly. Original-versus-composition outside the number region
was exact. Reviewed obsolete-number correction stayed pixel-exact outside its
approved plaque. Background promotion was native-pixel exact, and original/master
exports were opaque. Ownership cleanup was proven; the processor lease was released.

## Findings and narrow compatibility fixes

1. Current alpha preflight selected the bottom visible layer, SC3340's exact
   reviewed obsolete #054/100 text, as the resize background. It correctly rejected
   its transparent alpha before preparation. Background candidate selection now
   excludes only that exactly verified obsolete layer. The next artwork candidate
   must still pass complete native opacity and pixel-exact promotion proofs; no
   background is inferred, painted or generically exempted from validation.
2. ExtendScript numeric serialization rounded the fractional scale to 15 significant
   digits and strict float equality rejected the correct 9933 × 7024 result. Scale
   evidence now uses stable 12-decimal comparison; exact integer dimensions, target,
   policy, crop, budget, source and cache checks remain strict. A regression rejects
   materially wrong scale and even a one-pixel wrong output. The first failed native
   run's files/measurements are retained separately; it was not counted as success.
3. Files UI tests now exercise current Copy file selection and Download Original
   label, preserving their current behavior. Informational copy text describes the
   existing browser file-list limitation; it does not claim the removed PNG copy
   behavior. No download/copy/upload implementation changed.

## Equal-print-scale inspection

Retained local artifacts are under `output/v19/sc3340/`. The print JPEG is
`fractional-final/edition-059-TEST-NOT-PRINT-READY.jpg`.
`comparison-evidence.json` records metadata, hashes and measured process resources.
`overview-comparison.png`, `kobe-head-print-scale.png`, `jordan-head-print-scale.png`,
`title-print-scale.png`, both signature sheets and `edition-print-scale.png` compare
matching physical regions. Only comparison sheets resample the old JPEG for display;
the archived original and new production-pipeline JPEG are not edited for comparison.
Sheets carry 300 DPI metadata; actual screen magnification depends on the display.

Visual inspection: heads/photographic texture remain essentially the same underlying
detail; signatures and title retain shape/position; edition 059 remains centered in
the same plaque, with normal rerasterized edge differences and no obvious displaced
patch/mask. The overall canvas proportions and composition are retained. Exact
native pixel proofs supplement visual review; source canvas size does not prove
photographic detail. This is not a physical print proof or verified Prodigi quality.

## Tests and release compatibility

Focused Python suite: 165 passed, 15 skipped initially; the 14 optional SQL transport
cases were then rerun against an isolated PGlite dependency: all 32 transport tests
passed. The new actual PostgreSQL shared-variant context test and associated sizing/
onboarding API run passed (21 tests). The final combined run, with local SQL enabled, passed **181 tests** with no
skips, in 53.69 s. Evidence is recorded in Studio and `output/sc3340-final-tests.log`. No production credentials/data were used.
JSX model checks cover fractional/integer resizes, masks/coordinates, edition patches,
cleanup and reviewed/unreviewed obsolete-background selection. Six desktop/mobile UI
cases pass, including archived original download bytes and copy URL selection.
Topology validator passes. Renderer/encoder, original download checks and readiness/
fulfilment guards are compared against the current integration baseline.

Worker Health marks revision differences as Degraded; that compares revision IDs,
not semantic protocol compatibility. Installed marker was 5504669b, while Git/main
and Render were newer. The relevant installed preparation files were byte-equivalent
to current main before this patch, so that original warning alone did not demonstrate
a behavioral defect. This proposed release really changes companion preparation,
adds geometry/resolution modules and changes the preparation generation fingerprint.
The matching companion update is required: a server-only deployment would leave the
integer-only local preparer and could reject its undersized fresh package. No readiness
or allocation rule should be weakened to accept that package. Retained legacy archives
remain readable. No partial resumable sessions were found; transport settings, receipts,
DPAPI pairing, owner/task/port, scheduled startup and screen doer must remain unchanged.
Coordinate the idle companion update and canonical app release; do not restart the
screen task doer or activate gated resumable flags as part of this update.

## Outstanding supplier evidence

The actual Prodigi-uploaded asset, pixel dimensions, selected SKU, crop/zoom and
bleed remain unverified. These PPI values are estimates before supplier crop/bleed.
In the existing Prodigi order/editor, check the actual uploaded filename/asset
information (or download that exact asset if permitted), its pixel dimensions/hash,
product SKU and printable dimensions, orientation, crop/fit/zoom and preview. Compare
that asset hash with the archived original above. Do not submit or alter the order.
There is no verified universal Excellent threshold or guarantee of that rating.
Meeting raster dimensions does not recover original detail or explain the previous
rating without the uploaded asset/crop evidence.
