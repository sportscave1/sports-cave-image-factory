# Auto Editions V19 — native export investigation and local candidate

16 October 2026. **Local only; no measured native speed improvement is established.** The default exporter remains the V18 merged-duplicate path. The experimental path is restricted to an explicitly admitted local native benchmark. Real Photoshop comparison is still required before considering it for release.

## Verified base and isolation

Task `20261016-ec42ba64`, owner `codex-v19-native-20261016-01`, branch `codex/task/integrations-auto-editions-v19-native-photoshop-export--20261016-ec42ba64`. Its new isolated INTEGRATIONS worktree was advanced while clean to verified live revision `f7b4e39058710656406fd3dc89491c289069df26`, deployment `dep-db8nq46k1f9s73emkbgg`. Git ancestry confirms it contains the complete committed V18 release `5c9755441a3a7fafea6c150e5f359173e432d22a`. Unfinished automatic-visual-approval work in another task was neither copied nor incorporated. Existing worktrees and changes were preserved.

## What could be measured

| Measurement | Evidence | Conclusion |
|---|---|---|
| Current native baseline/candidate preparation, export median/p95 | Blocked before COM | Unavailable; no speedup or designs/hour claim |
| Current per-stage CPU, peak Photoshop RAM, scratch usage | No admitted native workload | Unavailable; no attribution to V19 |
| Admission resource observation | 5.86 GB available system RAM; 72.35 GB free temporary volume | Read-only observation, not workload peaks or actual Photoshop scratch capacity |
| Historical native open / inspection / master / number stages | 0.285 / 0.032 / 6.570 / 68.438 s, one earlier 2835×2004 local template run | Numbering was 90.9% of the four recorded stages, whose sum was 75.325 s. Not a current benchmark or population median/p95 |
| DOM control-flow model, 100-number workload | One source open and 105 PNG exports for both paths; 100 patch-document duplicates/closes removed in the candidate, replaced with 100 merges/history restores | Verified operation counts, not Photoshop time, rendering fidelity or speed |

Photoshop was installed and running (observed PID 28464), but the production companion processes were alive and its status was Uploading. The benchmark's preflight rejected admission even though no processor lock was present at that instant. A full benchmark command also exited with the explicit blocked result before creating its workspace, acquiring a lease or invoking Photoshop. No production process was paused, stopped, updated or benchmarked. Evidence: `output/v19/native-preflight.json` and `native-attempt.json`.

Thus the time-dominant **current native operation remains unproven**. The historical numbering stage warrants investigation; source inspection found the existing workflow already uses one PSD open and one Photoshop dispatch for the whole range. There was no repeated-open or per-number companion round-trip defect to fix. Each patch currently requires a full-canvas merged duplicate, crop, PNG save and close; their individual costs were not previously separated. PNG encoding, duplicate creation and history work must be measured before choosing a faster strategy.

## Implementation

- `scripts/photoshop/prepare_auto_editions.jsx`: lightweight native timers for open, inspection, ICC witness, resize, original/master/reference export, number-bound scan, text updates, merged duplicate, merge, crop, PNG save, patch close, history restore and staged-document close. Per-number durations and completed-number count survive failures in a separate `native-status.json`. Existing broad timing fields remain compatible. Inclusive/overlapping counters such as PNG save and reference export must not be summed as independent elapsed stages.
- Benchmark-only `history_merged_crop` candidate: merge the **full** staged composite before cropping, save the patch, then restore the exact layered history state and reacquire the editable number layer. Cropping layered artwork first can alter canvas-relative effects. The candidate eliminates patch document creation/closure but may increase merge/history/scratch costs; it has no proven speed advantage. No redraw/history preference, clipboard, resolution, font, ICC, PNG compression or JPEG setting is changed. The normal companion cannot select it through existing requests. [Adobe's JavaScript reference](https://community.adobe.com/havfw69955/attachments/havfw69955/photoshop/676381/3/photoshop-javascript-ref-2020-unlocked.pdf) documents the merge/history DOM; the mocked tests do not establish real Photoshop behaviour.
- `scripts/prepare_auto_editions.py`: optional explicit benchmark strategy, mandatory benchmark cleanup evidence, and source/staged byte-integrity checks even when native export raises. A JSON benchmark flag cannot bypass current-process lease ownership, live-host admission or the task-local source/output boundary. Native timing/cleanup diagnostics stay outside the immutable preparation manifest. Dispatch/final-trace overhead is separated from native stage time.
- `scripts/photoshop/benchmark_auto_editions_fixture.jsx` and `scripts/benchmark_auto_editions_native_v19.py`: create only new task-local synthetic, tagged RGB PSDs after exclusive admission. Reuse the existing non-stealable processor lease. Refuse active or idle production companions, unreadable ownership, held locks and insufficient resource budgets. Preserve pre-existing documents/dialog state; retain ownership if cleanup is uncertain. No network/provider calls exist in the benchmark.
- The runner alternates baseline/candidate order over at least three equivalent 100-number trials, records Photoshop version, stage timings, sampled CPU/RSS, per-trial logical working-file footprint, source fixture bytes and free-resource admission evidence. It reports local complete-preparation rate separately from number-stage time. This excludes Dropbox, queues, package/cloud transport and extra A/B acceptance-proof time. Three-trial p95 is the observed maximum, not a reliable tail estimate. Actual Photoshop scratch capacity remains explicitly unknown.

Acceptance compares all 100 patch pixels, the master, original and full numbered references; requires identical ICC bytes and all exported PNG metadata; verifies geometry, source identity and asset hashes; and requires an identical 300-DPI, quality-100, 4:4:4 JPEG preview. Unknown/volatile XMP differences also block acceptance until reviewed rather than being silently discarded. The existing independent Photoshop composition/original-pixel proofs and ICC preservation still run. A faster candidate with any failed proof cannot produce a successful benchmark summary or justify rollout.

## Recovery and quality protections

The normal V17/V18 processing path, priority order, terminal wake-up, Pause/Resume, retry rules, verified source/inspection cache, completed packages, cloud receipts and transport are unchanged. A local failure guard in `scripts/studio/auto_editions_local.py` now honours the durable dispatch/cleanup evidence: it releases the owner lease after pre-COM failures or proven document closure, and retains it after an uncertain returned RPC/export cleanup. It neither deletes nor steals an uncertain/foreign lock. The installed live companion was not changed.

Failed native attempts cannot create a valid preparation manifest or upload receipt. A retry uses the existing durable job/source recovery and a fresh staged output directory; partial unverified numbered files are not trusted or overwritten. This preserves safe whole-native-batch restart, not a new per-number resume-speed claim. Fully verified packages retain their existing resume/reuse behaviour. Uncertain Photoshop ownership requires owner review rather than letting another job enter an unsafe session.

Original PSDs are never saved; staged PSD hashes and original hashes must remain identical. The source mapping, edition total, numbering format, plaque/number geometry and all filenames remain authoritative. The PNG compression setting stays at 6, JPEG output stays at quality 100 with no chroma subsampling, and source ICC bytes are preserved/verified. Visual and supplier approvals remain mandatory under existing policies. No Shopify, allocation, certificate, queue, live Dropbox, companion installation or live configuration writes occurred; automatic approvals were not activated.

## Validation and handoff

The new Python tests cover admission before COM/lease/fixture creation, idle/unknown host ownership, held/foreign leases, low budgets, missing cleanup, strategy gating, all-100-patch comparisons, unsampled-number failures, ICC/metadata/JPEG conflicts, source mutation on failure, bounded per-trial footprint, and no overwrite of retained packages. Controller tests verify lease release for pre-COM/proven-clean failures and lease retention for uncertain cleanup. The ExtendScript DOM model verifies export count, default/candidate output equivalence in the model, history restoration, document ownership, dialog restoration, partial failure and uncertain cleanup. It makes no native rendering or performance claim. One inherited trailing blank line in the V18 SQL benchmark is removed solely for Studio's static whitespace check; its code is unchanged.

**Final regression: 185 passed in 87.82 seconds**, with the expected duplicate-ZIP fixture warning. The V19 DOM model and existing ICC JSX suite passed. Render topology validation passed. Evidence: `output/v19/final-regression.log`, native admission/proof logs, historical-native reference JSON and read-only cloud observation JSON. The work remains uncommitted and local; native performance acceptance remains outstanding.

Reproduction, only when production is independently inactive and ownership can be proven:

```powershell
python scripts/benchmark_auto_editions_native_v19.py --preflight
python scripts/benchmark_auto_editions_native_v19.py --output-root output/v19/native-comparison-NEW --repeats 3
```

The second command refuses an existing output directory and cannot stop a companion to obtain admission. Do not run it against an active preparation computer. Retain all trial outputs for all-number, metadata and resource comparison; the candidate must remain benchmark-only until representative native evidence supports it.

## Recommended V20 target

A read-only post-V18 cloud observation (one import, not a statistical baseline) recorded a 210.85 MB package received in 32.934 s at 6.1055 MiB/s, validation 17.707 s, Dropbox asset publishing 55.854 s, database save 4.404 s and server total before checkpoint 110.899 s. Publishing used one metadata listing and 101 uploads for 58.65 MB of assets, with effective publishing throughput 1.0014 MiB/s. V18's metadata-request reduction is present; repeated metadata lookup is not the remaining explanation. The observation and historical native evidence are separate cohorts and must not be ranked as one measured whole-design trace.

After completing V19's native comparison gate, target **per-asset Dropbox publishing and import acknowledgement latency**: distinguish the large master transfer, small-patch request latency, retries, verification and checkpoint acknowledgement over a representative cohort. Reuse existing immutable receipts and bounded upload sessions; establish the actual limiting stage before changing concurrency or transport. No cloud rewrite was undertaken in V19. No commit, push, merge or deployment is included in this local task.
