# Completed-changes release — 17 October 2026 AEDT

Owner explicitly authorised publishing all completed changes to Git/Render and
updating the Windows Companion, excluding the pending PSD-repair task.

Release task: `20261016-386c1800`, owner `codex-consolidated-release-20261017`.
Base: `bc0f901fc0c746ce8382c548930d8a3913eabb3a`, the current live/main release.

## Included

- Preserve already released catalogue/colour, product mockup protection, Editions,
  pre-generated review thumbnails, Orders V20, Worker Health, safe reset
  cancellation, Photoshop V19 and email publication work from the current main.
- Remaining EDITIONS changes from `20261016-4baac914`: ten-design review batches,
  scoped selection, compact navigation/counts, bounded preview loading, gap fill
  and preparation-aware selection retention; associated tests and read-only audit
  utilities. Retain the newer main reset-cancellation/status code.
- COMMERCE `20261016-2d1cd8d8`: immediate JPG preparation/delivery feedback,
  duplicate prevention, browser handoff receipt, timeout/navigation cleanup and
  retry of the existing prepared file. JPG generation, bytes and filename unchanged.
- EMAIL `20261016-9774fe3e`: shared subscriber-stage table, real persisted journey
  lookup, timing labels/countdowns, receipts and responsive sticky table details.
  No email sending, publishing, enrolment or schedule changes are run by release.
- Stabilise historical reliability benchmarks by pinning their pre-fix Git
  baseline rather than treating the moving HEAD as the old implementation.

## Explicit exclusion and preservation

No code or assets from the in-progress PSD-repair task `20261016-d1883a9f` are
included. In particular, its modified Photoshop preparation scripts and its new
number-text/recovery/PSD-audit helpers are excluded. Current released Photoshop
script bytes are retained. No original PSD, mappings, numbering, allocations,
certificates, review approvals, orders or customer records are changed by this
release. Other task worktrees remain intact. Superseded prototypes and local
screenshots/caches/test output are not substituted for current released code.

No migration, schema manifest, Render topology, requirements or feature-flag
changes are introduced. Existing ICC-policy bytes and the Companion's disabled
automatic visual approval setting remain intact. No live backfill or test design
submission is part of the release.

## Verification and operations

Tests use isolated HTTP/Streamlit fixtures and disposable PGlite databases.
Verify ten-card navigation/selection/live updates/expiry and stale preparation,
native JPG bytes/name/handoff/duplicates/retry/deadlines/responsiveness, subscriber
stage persistence/UI, review/cache/thumbnail guards, cancellation and Worker Health.
Run existing Render topology and Studio verification before publication.

Deployment uses the established main auto-deploy, preserving the canonical
`sports-cave-os` service `srv-d8kl4on7f7vs73dvavv0` and existing supporting services.
For the Companion update, stage committed Git bytes, verify policy/code hashes,
pause new claims using existing audited control, wait for a safe idle boundary,
switch only the proven idle Companion process family, verify fresh heartbeat and
restore the prior claim setting only if this release still owns the pause.
Photoshop, Dropbox and unrelated Studio workers must stay running.

Actual test results, deploy IDs, commit, Windows runtime hash/heartbeat and
limitations are recorded locally in the release worktree's
`output/consolidated-release/` directory after execution.
