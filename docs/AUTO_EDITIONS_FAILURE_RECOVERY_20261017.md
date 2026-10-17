# Auto Editions failure and preview recovery — local review

Task20261017-ca973a3a, owner codex-recovery-20261017. Verified task worktree and
branch; baseline is live/main7e957f4c. Original repository and other worktrees are
untouched. No commit, deployment, production retry or live policy write has been
performed by this task. A separate colour task owns its27 already accepted jobs.

## Confirmed causes and prepared corrections

The technical consumer acquired the approved registry only when a separate colour
backend environment switch was present. Volkanovski's exact source matches the
existing approved policy, but the Render job could not resolve it. The local fix
reads existing configuration once per technical job and refreshes it within the
final transaction fence. Strict source/policy/ICC and technical evidence checks
remain mandatory. A policy changing before commit fails closed.

Legacy thumbnails were rejected because receipts lacked byte counts and PNGs had
no ICC. Exact provider IDs/revisions and downloaded bytes were checked. A separate
preview-only validator verifies immutable manifest SHA, geometry, identities and
preservation proofs, accepting missing legacy byte counts without editing stored
receipts. Untagged RGB preview values remain unconverted and receive an explicit
legacy/unverified-colour note. Approval and technical validators still reject
missing ICC or incomplete current receipts. Existing valid thumbnail cache keys,
bounded builders, progressive loading and retry controls are retained.

Explicit export repair reuses the existing preserved replacement pipeline, never
Reset.clear. It retains mapping, old preparations and history; queues one pinned
source only; guards current failed checkpoint, source, mapping, priority and all
active leases. Discovery rejects a changed provider revision instead of switching
sources. Ordinary Retry remains verification-only; explicit repair confirmation is
required for re-export. No edition allocation, certificate or supplier writes.

## Original seven failures

All six untagged PSDs below were inspected read-only from local Dropbox copies.
Current provider revisions and full independently computed Dropbox content hashes
match their authoritative preparation sources. Each has the exact approved legacy
OriginalDocumentID, DerivedFrom and complete four-event Photoshop creation/save
history, with a valid unique final save instance. This is independent provenance,
not filename/size inference. Six proposed content-bound workflow receipts were
prepared through existing verified_membership(); they are not activated yet.
Their downloaded number-1 PNGs match authoritative manifest SHA256 and lack ICC.

| Design / product ID | Confirmed cause | Prepared recovery / remaining validation |
|---|---|---|
| Alex Volkanovski UFC Champion /10071572578611 | Existing exact approved policy not loaded by Render consumer | Deploy consumer correction; retry retained technical verification. No new approval or PSD regeneration required. Full current cloud validation must still pass. |
| The Greatest Tyson VS Ali /10111633260851 | Untagged source previously lacked registered provenance; retained PNG lacks ICC | Activate verified membership; explicit pinned export repair through serialized Companion. |
| The Immortals Gretzky vs Lemieux /10115555754291 | Same, independently verified | Same guarded repair; original source untouched. |
| The Titans Ruth vs Gehrig /10115562111283 | Same, independently verified | Same guarded repair; original source untouched. |
| The Summer of '98 Sosa vs McGwire /10135814963507 | Same, independently verified | Same guarded repair; original source untouched. |
| The Legacy Montana vs Marino /10139331395891 | Same, independently verified | Same guarded repair; original source untouched. |
| Ken Griffey Jr. The Kid /10155671650611 | Same, independently verified | Same guarded repair; original source untouched. |

All seven have an evidence-backed recovery path. None is reported recovered or
Cloud Ready until the authoritative preparation/verification actually succeeds.
Fresh native results for the six have not been run; the Companion is busy on the
separate authorised colour queue. Its Photoshop/upload ownership was preserved.

## Actual measurements and checks

Original broken assets: two11340x8016 RGB masters,45,852,011 and46,414,095 bytes;
both masters and both number patches are genuinely untagged. Provider downloads
took3.51s/4.97s for masters and1.83s/1.64s for patches, once for inspection.
With exact downloaded files through the actual image handler locally:

| Design | JPEG | Cold image resolution | Warm response |
|---|---:|---:|---:|
| Alan Kulwicki — Underbird |300px /18,575bytes |1,259ms |1.39ms |
| Allan Moffat — 500 Miles Alone |300px /19,340bytes |1,103ms |1.23ms |

Initial handler acknowledgement was202 in158ms/1.63ms; completion was HTTP200.
Warm requests reused identical cached JPEGs with zero further asset fetches.
These are local handler measurements using real retained artwork, not a claim
about live Render/Dropbox request timing. Before: strict evidence rejected both
legacy records before image rendering. Original records/bytes remain unchanged.

Focused final suite:89 passed in141.19s, including technical processing, duplicate
and repair guards, numbering preservation, legacy reset compatibility and desktop
Worker Health285-row HTTP/browser checks. Two additional pinned-discovery scenarios
passed in4.46s (unchanged source queues; changed source fails and retains mapping).
An earlier fixture lacked the legacy replacement migration; fixture corrected and
repair rerun passed. A compatibility error-message mismatch was corrected and its
regression passed. Existing optional dependency deprecation warnings remain.

## Queue progress and safety

At12:21 AEDT:31Pending/13Failed. At12:38 AEDT:21Pending/23Failed. The queue has
continued reaching durable terminal results, rather than freezing. These failures
are real technical outcomes, not successful recovery. Original37 queued jobs had
advanced by16 additional terminal outcomes since the prior release report.
Render and Companion both report Live at7e957f4c. A short native test pause owned
by the separate colour task was respected and released by that owner.

Edition-number field fingerprint was identical at12:26 and12:38 AEDT. Cloud Ready
count83 and certificate count1072 were unchanged. No Photoshop commands, process
stops, worker restart, queue-wide retry or Dropbox write was performed by this task.

## Files

auto_editions_bulk.py; auto_editions_preview_evidence.py;
auto_editions_technical.py; auto_editions_reset.py; worker_health_queue.py;
components/auto_editions/bulk.html; tests/test_auto_editions_recovery.py; this report.
Detailed source evidence, proposed receipts, exact artwork checks and test XMLs
are retained under ignored output/recovery. Download tokens are not committed.

## Activation boundary

Repository AGENTS.md requires fresh explicit approval to commit/push/deploy or
mutate production. After approval: publish this narrow fix, wait for an upload-safe
deployment boundary, verify live health, register only the six still-current
verified memberships, retry Volkanovski technical verification, and submit six
explicit export repairs through the existing authenticated queue path. Recheck
success/deferred/current-operation state before each acceptance. Do not touch the
separate colour task's targets or passed designs. Existing Companion code is
unchanged and does not need interruption to run this server-side correction.

## Owner-authorised release

On17October the owner explicitly authorised Git publication, Render deployment,
Windows Companion update and the scoped recoveries. Publish the tested recovery
and preview fixes. Earlier completed Bulk Review, Worker Health, reset, automatic
technical flow, Orders and email work is already in origin/main7e957f4c.
Preserve unfinished Product Upload PSD intake (native/storage end-to-end checks
outstanding), the ongoing PSD repair and superseded development prototypes.
No Render topology or migration changes. Switch the Companion only at a verified
idle boundary and retain native helper/policy bytes. Record actual deployment,
recovery and protected-data checks in output/recovery/release evidence.
