# Companion background-selection recovery

Investigation: task 20261030-0de2f76d, starting production revision
66e682aa2e99476b16e6fffc1da73dc20aba1394. User authorised investigation,
shared repair, recovery and deployment; no customer emails or print orders.

## Confirmed failure

William Contreras (Shopify product 15451087438131) was manually mapped at
00:05:08 UTC on 30 October. Automatic claim followed at 00:05:50; preparation
failed at 00:12:13. The source and original failure journal remain retained.
The pixel guard correctly rejected a changed composition. Native reproduction
isolated the change to `isBackgroundLayer=true`, not rasterization: Photoshop
also reveals the active layer. This PSD had an obsolete hidden composition
selected. Selecting the verified background candidate first produced identical
RGBA pixels and preserved all other layer visibility. The source PSD is never saved.

No completed package existed for this design. Historical backlog scanning was
release-gated and restricted to a fixed ordered-product list. New designs could
therefore prepare automatically once, but were excluded from that recovery path.
The old Companion also reported revision `local` because its release marker was
absent. Recovery now uses authenticated content evidence for the relevant native
files, independent of unrelated web releases.

## Shared changes

- Select the pinned visible layer before background promotion. Preserve the
  exact-pixel, opacity, geometry, ICC, source and upload verification gates.
- Run routine recovery with the existing technical-preparation workflow. Keep
  exceptional historical native/role repairs behind their existing rollout gate.
- Admit this deterministic failure once per source and relevant native fix,
  only with a fresh idle Companion reporting matching native code and no lock,
  retained checkpoint or recovery failure. Never reset completed preparations.
- Admit evidenced transient failures with durable bounded retries and capped
  backoff, including designs outside the historical list. Reuse lease fencing,
  idempotent queue requests and resumable package checkpoints.
- Corrected inventoried source bytes and approved colour evidence can resume
  through the same guarded service; exact blockers remain visible otherwise.
  Manual mapping, colour authority, allocations and retained assets are unchanged.
- Name the native background failure in diagnostics instead of reporting an
  undetermined cause. Queue admission never grants Cloud Ready.

## Validation before release

171 focused Python tests passed, covering preparation, queue, technical completion,
upload lost acknowledgements/restarts and duplicate work. The final recovery suite
passed 26 tests, including the added corrected-input case. The native JavaScript
selection regression passed for raster and smart-object cases. A fresh synthetic
Photoshop document with a hidden active layer passed the real shared native block
with exact RGBA pixels. The failed PSD's corrected native promotion also matched
exactly. Existing original files and diagnostic outputs remain outside Git.

Four discovery-suite failures also reproduce on unchanged production code (two
missing dependencies in the system Python and two stale test expectations).
Scoped Studio verification, topology validation and whitespace checks pass against
the actual production base. The registered task's older base includes unrelated
previously released whitespace issues; those files are not changed by this fix.

## Release and live acceptance

Use the existing main-branch Render deployment and existing scheduled Companion
identity. Install an immutable release tree, include its release marker, and use
the existing close endpoint which refuses active preparation/checkpoint work.
Preserve scheduled-task settings, journals, profiles, tokens and the old runtime.
Do not manually insert/retry the product: observe automatic scanner admission,
native preparation, upload receipts and successful technical verification.

Live deployment IDs, preservation hashes and final recovery evidence are recorded
in the task's ignored output directory and final user report. This document's
pre-release tests alone do not claim production recovery or supplier approval.
