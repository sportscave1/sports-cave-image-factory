# Final companion speed release — 20 October 2026

The owner explicitly authorised final review, improvements, commit/push, Render
deployment and Windows helper update after Phase 5. This one release supersedes
the local-only boundary in the historical Phase 4/5 reports. No unrelated active
task, customer recovery, allocation, certificate, source PSD or colour approval
is authorised to change.

Task `20261020-06c0d1d1`, owner `codex/companion-phase4-20261020`, branch
`codex/task/integrations-companion-phase-4-local-processing-and-pac-20261020-06c0d1d1`.
The original Phase 1–3 worktree remains Released. Current production commits
through `2859b999` (Task Recorder and lifestyle prompt work) were merged without
conflicts; their source and other worktrees were preserved. The final code
revision is the commit containing this report, shared by the release branch,
main, Render and the installed helper once release verification passes.

## Reviewed and retained

- Photoshop full-composite merge/crop/history restore, exact layer-ID recovery
  and 4 GiB available-memory fallback. Three paired retained trials saved
  **28.287s / 20.15%** local edition preparation; all 104 PNGs/ICC/edition
  placement and TEST JPG equivalent. ~730 MiB additional Photoshop peak RSS is
  the documented trade-off; no persistent preferences changed.
- Product Uploads preserves the exact Ruth source approval. Current server
  workflow remains WEBP-only. Private lossless PNG compression and redundant
  native checksum work were improved; current server processing saved
  **0.07565s / 2.23%**, with identical final assets and +1.58 MiB private PNG.
- One aggregate streaming upload budget/slot, bounded bursts, source/recovery
  paths and retries. Higher configured rates no longer routinely underfill
  because of the old Windows token-bucket ceiling. No concurrency increase.
- Balanced/Background calibration, bounded adaptation, hysteresis, persistence,
  authoritative Manual and unchanged owner-selected Maximum. Capacity is never
  inferred from capped speed, server verification or the historical 0.380 MiB/s.
- Safe pause wording, requested/effective settings, payload progress/ETA, recent
  failures vs backlog failures, and separate uploaded-verifying/Cloud Ready.
- Durable resumable code, strict identity/offset checks, publication receipts,
  loss/restart recovery and a separate default-closed acceptance gate. Legacy
  uploads remain available. No old partial packet is relabelled/regenerated.
- Bounded correlated per-job summaries and body timing; proxy/connection gaps
  remain explicitly unknown. The historical **288.020s is still unexplained**.

Final review added one fail-closed recovery improvement: after a chunk-boundary
pause, a server offset below the last confirmed offset is rejected before any
more bytes. A real isolated SQL/provider/HTTP regression proves zero retransmit
in that failure. Optional calibration also ignores response objects without
numeric HTTP status; it cannot break otherwise validated upload/cache reuse.

## Validation and release boundary

The integrated speed/colour/recovery/health suite initially passed 247 tests,
with one known skip and one known baseline deselection, and exposed the optional
response-status compatibility case. It was corrected and the affected Product
Uploads/cache-reuse, shared controller, Phase 5 and preparation-host tests were
rerun: **59 passed, 1 known baseline deselected**, with three existing dependency
warnings and no remaining failure. Exact results are retained under
`output/companion-final-release/{integrated-tests.log,final-boundaries.log}`.
V19 DOM model, Phase 3/5 desktop/narrow UI checks, topology, whitespace and Studio
checks are included. Earlier real Photoshop and 209 MB packet-equivalence
evidence is reused, not repeated as a production benchmark.

Release uses the canonical existing Render primary and existing supporting
webhooks/SEO services. No Blueprint/resource creation, new migration, new
provider service or automatic backlog release. The single premature flag is
corrected to `COMPANION_RESUMABLE_UPLOADS_ENABLED=false`, preserving other
environment values. Historical Phase 5 configuration JSON is the original
prepared plan; the actual authorised correction is recorded with live evidence.

**Resumable new sessions stay disabled.** Native multi-process PostgreSQL
restart/locking, real-provider durability/permissions/partial publication and
expiry/retention acceptance remain outstanding. Local PGlite/provider fixtures
do not satisfy them. Acceptance marker, exact generation and reviewed report
hash are required before a separately authorised activation. Deploying the code
does not mean the protocol is enabled or accepted.

Before runtime changes, verify zero owned active preparation leases/upload
sessions and an idle companion; gracefully close the existing supervisor, never
kill active processing. Export the exact final Git tree into a new immutable
installed-release directory. Backend first, helper second. Change only the
existing scheduled task's runtime action, preserving owner, triggers and
settings. Retain the prior installed release for rollback. Settings, source
approvals, journals, receipts and partial packets remain in their existing homes.
Maximum/request_5670 is preserved; no automatic calibration stall in that mode.

## Completion evidence

Git/Render deploy IDs, exact revisions, normal-supervisor helper verification,
settings and journal hashes, active-work checks, flag probe, authorised live UI
checks and final service status are retained in the local release evidence
directory `output/companion-final-release/`. That evidence, not the act of
requesting deployment, establishes the final live outcome. The user-facing
completion report identifies the actual commit and any remaining acceptance
limitations. Retain this worktree and fixtures for audit/rollback.

No measured live speed or household browsing improvement is claimed. The
processing/controller changes are supported by local matched evidence; normal
authorised production telemetry can assess their live effect later. Further
speculative speed optimisation is closed for this release.
