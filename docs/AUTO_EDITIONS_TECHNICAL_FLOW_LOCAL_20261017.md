# Automatic technical Auto Editions — local implementation, 17 October 2026

Status: implemented/tested locally, uncommitted. No production reconciliation,
migration, deployment, approval, remap, upload, worker update or restart was run.

## Isolation and baseline

Task `20261017-b660fa07`, owner `codex-auto-flow-20261017`.
Worktree: `C:/Dev/SportsCaveWorktrees/sports-cave-editions-automatic-technical-auto-editions-processi-20261017-b660fa07`.
Branch: `codex/task/editions-automatic-technical-auto-editions-processi-20261017-b660fa07`.
The idle EDITIONS category was clean. Studio created an isolated task; its clean
checkout was advanced to `67f8e091`, subsequently verified live on the canonical
Render service at 00:17:39 UTC. Other releases continued independently afterward.

The baseline includes colour implementation `98a75196` and its follow-up
`272c1342`. Coordination was sent to the colour task. Its release authorization
has not been extended to this task. Pending PSD repair task `20261016-d1883a9f`
was excluded; none of its detection, renderer, repaired-copy or mapping proposals
were copied. Original/category/other task changes remain intact.

## Removed prerequisite and resulting flow

The old package endpoint persisted valid uploaded packages as Blocked until a
layout carried visual approval. Status and download resolution depended on that
approval too, so hiding the button alone could not remove the gate.

With `AUTO_EDITIONS_TECHNICAL_FLOW_ENABLED=true`, the package/checkpoint path and
existing Auto Editions discovery consumer perform technical completion. Normal UI
states are Not Mapped, Uploading, Cloud Ready and Failed. Queue stages, priorities,
leases, attempts, reset cancellation and technical failures remain distinct in
storage/details. Queued Uploading rows remain categorized as queued in Worker
Health; they do not pretend to be active Photoshop work.

`auto-editions-technical-v1` records exact TEST readiness in the existing layout
contract. It contains no `visual_approved`, human review or AI review claim. It
cannot create supplier certificates. Supplier reconciliation explicitly excludes
new technical-only layouts. Existing approval records/history are preserved;
restricted allocations or conflicting variants cannot be silently broadened.
Historical immutable manifest fields such as `quality_approval_required` are
retained without rewriting hashes; they are not used as artwork-acceptance gates
by the new technical readiness method.

Source/hash identity, approved PSD location, stored inspection/role/font checks,
complete numbered-patch range, original/full-range geometry contract, first/last
pixel proofs, outside-number preservation, PNG geometry/checksums/ICC and real
cloud receipts remain required. New native preparation still runs the unchanged
Companion scripts, including every-number bounds measurement. No edition counter,
order allocation, certificate, inventory or Shopify record is written here.

## Colour policy reuse

No new colour implementation or profile assignment was introduced. The new path
calls the released `auto_editions_colour_policy.resolve()` and existing workflow
membership logic. It reuses the owner-approved Volkanovski policy and
`legacy-rgb8-verified-workflow-default` only for covered pinned sources. An
untagged retained RGB8 package must have applicable existing approval, and its
actual exported ICC fingerprint must match that policy. CMYK/unknown colour
exceptions fail with an actionable reason. Valid tagged profiles are preserved.
No original or staged PSD profile was changed by this task.

Read projections share one colour configuration snapshot per batch rather than
querying policies for each row. Status polling does not select whole manifests.

## Durability and recovery

An additive, server-only RLS-protected table stores technical checks. Its identity
includes product, preparation hash and checkpoint generation. Atomic claims use
exclusive row ownership and expiring tokens; verification performs file/provider
I/O outside the final database transaction. The commit fences checkpoint
generation, source, mapping, edition limit, current proof/receipt contents,
colour policy, resets and layout scope.

The package checkpoint is durable before technical work starts. Fresh imports
reuse already uploaded local generated assets. Closing a window or losing its
response does not remove the checkpoint. The existing preparation discovery
thread seeds up to 100 missing checks and drains one per cycle; it resumes
pending/expired claims after restart. It also recovers retained Awaiting
preparation checkpoints without starting Photoshop again. Interrupted or
recognized transient checks have a three-attempt bound (60-second retry delay,
45-minute claim bound). Permanent validation failures stop and expose Retry/
Repair. Same-hash reset/remap generations cannot accept old completions.

Missing/incomplete receipts can be recovered only through actual immutable cloud
metadata plus byte/ICC verification. Previous and recovered receipt values are
audited. Missing files become a technical failure requiring restoration or a
supported retained-package upload; no receipt or success is invented.

The existing preparation/discovery consumer in `sports_cave_worker.Supervisor`
must receive this release alongside the web application when separately
authorized. No new service, Photoshop process, worker concurrency or unrelated
CRM/SEO processing path was added. The installed Companion and its launcher were
not edited. The existing serial Photoshop lease/processor lock remains in force.

## Read-only backlog dry run

Authoritative checkpoint export completed at **2026-10-17 00:35:58 UTC**
(11:35:58 AEDT). Classification uses the released committed approved registry;
the read-only policy/workflow audit query returned zero additional records.
This is a fixed snapshot; the separate colour release continued independently.

| Classification | Designs |
|---|---:|
| Protected Cloud Ready | 83 |
| Protected deferred/excluded | 3 |
| Prepared candidates for current-source/cloud verification | 10 |
| Retained preparation requiring immutable receipt recovery | 1 |
| Technical failures | 188 |
| Total | 285 |

Of 45 retained Blocked preparations, 33 lack applicable approved colour coverage,
10 have sufficient stored evidence to attempt verification, one needs receipt
recovery and one is deliberately deferred. The 188 technical failures comprise
those 33 colour exceptions and 155 other unprepared failures. The other two
deferred entries are unprepared. No Preparing/Awaiting preparation rows remained
in this final snapshot. Lingering terminal lease timestamps are not claimed or
cleared by the dry run.

**Candidates are not verified successes.** No cloud assets were downloaded or
live work retried for this dry run. Full per-design results:
`output/technical-flow/final-backlog/backlog.csv` and `backlog.json`.
Read-only source export: `backlog-final-input.json`. Reproducible classifier:
`scripts/audit_auto_editions_technical_backlog.py --snapshot <export.json> --output <directory>`.
Use the existing approved colour registry configuration when classifying.

## Verification and measurements

- Compatibility/integration run: **212 passed, 1 skipped**, 216.72 seconds. Covers
  status, onboarding permissions, bulk review, colour policies/workflow reuse,
  reset/mapping safety, Worker Health and supplier quality. The skipped test is
  an optional native benchmark. Two existing websockets deprecation warnings.
- Final technical suite: **30 passed**, 54.18 seconds against disposable PGlite
  and actual generated PNG/ICC bytes, including actual package archive/HTTP
  handler, automatic completion without visual approval, asset corruption,
  missing receipts, fonts/proofs/source failures, exclusive claims, restart and
  retry bounds, same-hash reset generations, duplicate submits, restricted layouts,
  deferred/passed preservation, colour revocation, RLS and Worker Health retry.
- After the final claim-eligibility tightening: **3 passed**, 5.92 seconds
  (mapping-to-queue, actual package completion, retained-checkpoint recovery).
- Real Edge desktop/mobile checks pass for preview-only controls, detailed
  Uploading spinner, automatic Cloud Ready transition, larger previews, no artwork
  approval requests, and no overlapping status requests. Synthetic loopback
  first thumbnails: **128 ms desktop / 93 ms mobile**, **2,171-byte JPEG**. These
  measurements are not Dropbox or real-catalogue/native preparation benchmarks.
- Existing Worker Health Edge checks pass with 334 synthetic rows, continuous
  scrolling, details, recovery and failures. Latest first paint: 237/198 ms
  desktop/mobile; no diagnostic-log reads on initial load.
- Existing 100-edition Photoshop DOM control-flow and ICC-inspector models pass.
  These are models, not new native Photoshop executions.
- Fresh-import test observes **zero generated-asset downloads and one current
  source metadata request** after the verified publish step. Retained cold checks
  still depend on real Dropbox file/metadata latency; that latency was not measured
  against live files in this task. Dry-run classification: approximately 354 ms.
- Compile checks, JavaScript syntax checks, migration mirror/hash checks,
  `git diff --check` and Render topology validation pass.

An actual Photoshop process remained running (PID 31732); Companion telemetry
showed a separate release's Uploading work during this task. No independently
owned isolated Photoshop environment was available. Consequently no new native
Companion run or live end-to-end reconciliation is claimed.

## Changed files

Backend: `auto_editions_technical.py` (new), `auto_editions.py`,
`auto_editions_setup_api.py`, `auto_editions_onboarding_api.py`,
`auto_editions_onboarding_store.py`, `auto_editions_discovery.py`,
`auto_editions_priority.py`, `auto_editions_status.py`, `auto_editions_store.py`,
`auto_editions_bulk.py`, `auto_editions_quality_store.py`, `worker_health.py`,
`worker_health_api.py`, `worker_health_queue.py`.

UI: `edition_auto_status_ui.py`, `components/edition_auto_status/live.js`,
`reset.js`, `bulk.js`, `components/auto_editions/status.html`, `bulk.html`,
`components/worker_health/index.html`.

Schema/config: `.env.example`, `run_migrations.py`, mirrored
`20261017001547_auto_editions_technical_completion.sql` under `migrations/` and
`supabase/migrations/` (created with the Supabase CLI, not applied).

Verification/report: `scripts/audit_auto_editions_technical_backlog.py`,
`tests/test_auto_editions_technical.py`, `tests/test_auto_editions_technical_ui.cjs`
and this report. Generated evidence stays under ignored `output/technical-flow/`.

## Release boundary

The feature is **off by default**, including in `.env.example`. Local tests enable
it in isolated processes. A future specifically authorized release must apply the
reviewed additive migration and enable `AUTO_EDITIONS_TECHNICAL_FLOW_ENABLED=true`
on the existing web and preparation-worker runtime with the released colour
configuration. That activation starts backlog reconciliation; it has not happened
in this task. Existing deliberate Deferred/excluded entries remain protected.
No commit, push, deployment or live backlog execution is authorized by this report.
