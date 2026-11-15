# Companion backlog recovery — local implementation, 18 October 2026

## Identity and boundaries

Continued task 20261017-37907e10, owner
codex-01a14756-post-upgrade-20261018, in the existing worktree
C:/Dev/SportsCaveWorktrees/sports-cave-integrations-recover-windows-companion-after-ssd-migrat-20261017-37907e10.
Branch: codex/task/integrations-recover-windows-companion-after-ssd-migrat-20261017-37907e10.
Starting HEAD: c71943ef3a07b2873e295f210ec4092790d7ba51; initially clean.
The supplied editions folder was an idle category entry point and was not edited.

Read-only authoritative Supabase heartbeats independently reported Render and
Companion at this exact revision. Companion was Idle, without a processor lock or
pending checkpoint. The immutable installed-release marker agrees.

No commit, push, merge, deployment, live source edit, production retry/requeue,
Companion restart, Photoshop operation or cloud upload was performed. Tests use
disposable PostgreSQL and synthetic PNG/ICC data. Production snapshots are kept
outside Git and are never loaded into application previews or tests.

## Full backlog and historical reconciliation

Read all 286 queue rows, current retained manifests/proofs/receipts, current
technical failures, all approved colour-policy/workflow receipt events and all
286 mapped inventory metadata records. No UI page limit was used.

110 existing Cloud Ready checkpoints were protected, not downloaded or rerendered.
176 failures were classified:

| Current failure group | Total | Candidate recovery | Needs review/deferred |
| --- | ---: | ---: | ---: |
| Plaque / editable number / formatting | 66 | 0 | 66 |
| Explicit colour / provenance failures | 40 | 11 | 29 |
| Upload / transfer / network | 14 | 7 | 7 |
| Photoshop / generic preparation errors | 50 | 0 | 50 |
| Immutable receipt lookup | 1 | 1 | 0 |
| Transfer-size limits | 3 | 0 | 3 |
| Other, deliberately excluded/deferred | 2 | 0 | 2 |
| **Total** | **176** | **19** | **157** |

These are eligibility candidates, not completed uploads. Admission repeats source,
policy, mapping, lease, reset and checkpoint guards; final success requires the
existing byte, ICC, export and immutable cloud-receipt verification.

The 11 colour candidates comprise nine tagged-source export repairs and two
retained untagged sources covered by existing exact approvals. The 29 other
explicit colour failures lack sufficient approved source-group provenance. No
membership receipt, default-policy extension or sRGB approval was invented.

All 42 generic RuntimeError failures date from 15 October, before the existing
ICC preservation fix b177b3ea (16 October). Their retained job identities and
current-revision inspections match; metadata-only inspection of their archived
input PSD headers found all 42 untagged. Their current approved-policy lookup does
not authorise assignment. This explains why a generic historical error is not
evidence that a retry will succeed. The observation is diagnostic only, not a
new provenance receipt. Subsequent matching approved provenance makes the shared
classifier reassess these jobs without individual code patches.

The current inventory shows no changed source content among the failed jobs.
Existing local diagnostic files were reconciled by pinned source identity.
Source revision changes with different bytes can trigger a bounded new inspection;
metadata-only revisions do not reprocess unchanged deterministic structural errors.

The historical colour strip (115 affected / 76 recovered / 39 unresolved) is a
different projection from current failure categories. It must not be subtracted
from the complete failed backlog or interpreted as remaining runnable work.

The validated shared template explicitly grants layer-naming scope only.
Its dimensions, generic plaque name or geometry cannot identify a missing or
ambiguous target in another artwork. The 66 structural failures retain precise
number/plaque/formatting reasons and remain Needs review.

## Shared implementation

* auto_editions_recovery.py: full-queue planning; startup and 60-second periodic
  scanning in the existing discovery worker; at most three provider/admission
  attempts per cycle. Durable per-source/relevant-policy/shared-fix audit keys,
  transactional admission, duplicate prevention and retained attempt history.
  Deterministic recovery gets one admission per evidence key; proven transient
  recovery gets at most three with 60/120-second backoff. The existing native
  worker independently caps its execution attempts. Failed admission is journalled
  too, preventing a bad source from monopolising later cycles. Active leases and
  administrator pause are preserved; no completed state is created by scanning.
* worker_health_queue.py and auto_editions_onboarding_api.py: both manual Retry
  routes and automatic admission share the guarded service. Failed native
  replacements retain their original reset identity and previous package.
  Retained export repairs use Technical.repair_exports and Reset.request.
* auto_editions_technical.py: missing-receipt recovery previously passed a package
  path to the immutable-ID-only source helper, producing Invalid Dropbox file ID.
  It now reads only the validated canonical package path, verifies the returned
  path, then runs normal immutable receipt, byte, ICC and current-source checks.
* auto_editions_discovery.py: runs the release-gated scanner independently of
  individual Retry clicks. A scan/admission failure does not stop technical
  verification or other candidates.
* worker_health.py and components/worker_health/index.html: compact runnable,
  active recovery, verified and Needs review counts, failure categories and
  explicit disabled/stale/wait/backoff reasons. Full scan telemetry shares the
  existing snapshot SQL, retaining the two-query read budget. Needs review is a
  read-model status, preserving original queue/checkpoint/error records.
* scripts/audit_worker_recovery.py: repeatable offline full-snapshot reconciliation.
  Local header observations never authorise a profile assignment.

Existing native preparation preserves valid embedded profiles, assigns an
approved profile only to demonstrably scoped untagged bytes in staging, preserves
the original PSD, checks the Photoshop profile witness and verifies output ICC
before upload. Those controls were reused; no artwork or profile handling was
weakened. Valid packages resume at technical verification; only evidenced export
failures enter guarded replacement.

Tests changed: tests/test_auto_editions_backlog_recovery.py,
tests/test_auto_editions_technical.py, tests/test_worker_health_ui.cjs.
No render.yaml, installed helper, live credentials or live source was changed.

## Validation and retained evidence

Focused checks cover more than 50 jobs, duplicate scans, durable retry ceilings,
backoff, active leases, pause, source changes, unrelated policy changes, peer
progress, guarded retained repair, immutable receipt recovery and Needs review
health projection. Existing colour tests exercise preservation of different valid
embedded ICC profiles and rejection of unknown sources/conflicting profiles.
Desktop (1280px) and mobile (390px) browser checks exercise compact recovery counts,
continuous queue scrolling and manual controls. The JSX ICC contract passes.
Render topology validation and git diff --check pass.

The combined focused Python suite passed 163 tests (2 warnings). After the final
lease-fairness adjustment, all 10 scanner tests passed again. Both Worker Health
browser widths, the JSX ICC contract, eight direct Python syntax checks, Studio
Verify, topology and whitespace checks passed. No production completion is claimed.

Read-only queue, inventory and policy snapshots plus the per-design audit:
C:/Dev/SportsCaveWorktrees/.studio/release-evidence/companion-backlog-20261018-37907e10.
All retained originals, backups and completed preparations remain in place.

## Exact future release / activation

Separate explicit owner authorization is required to commit, integrate, push and
release this tested change. Select the exact approved commit; deploy it to the
existing canonical sports-cave-os (srv-d8kl4on7f7vs73dvavv0) and the existing
worker service running sports_cave_worker.py. Preserve the supporting service
topology and existing technical/discovery/continuous-processing flags.

Set AUTO_EDITIONS_BACKLOG_RECOVERY_ENABLED=true on that existing worker and on
the canonical app for consistent Worker Health reporting. The new path supersedes
the older colour-only claim hook while this flag is enabled. No migration, new
service, Blueprint sync or bulk-requeue command is required.

Use the established idle-only Companion bundle update flow to align its release
marker with the same approved SHA; the native processor code is unchanged.
Never restart an active preparation or clear an uncertain lock.

On worker startup, and then each minute, the scanner admits eligible jobs in
bounded batches through the shared service. Leave existing manual pause/resume
and Retry controls available. Verify fresh scan telemetry, authoritative runnable
claims, preserved leases, declining eligible backlog, and newly verified export/
cloud receipts. Do not report the 19 candidates as uploaded until those checks
actually succeed. The 157 blocked/deferred jobs remain protected; matching
provenance, relevant shared fixes or corrected source bytes trigger reassessment.
