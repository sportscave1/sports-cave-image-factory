# Developer Studio Phase 4B / 4C — local release dry runs

This implementation extends the owner-only in-app Developer Studio. Production publishing is disabled in both the interface and local API. No hosted filesystem, shell, Docker or provider credentials are introduced. Live revision, GitHub branch, service health and release history remain **unverified** until a trusted provider verifier exists. Mock receipts never populate Live.

## Workflow

Run the existing Studio `DraftUI` launcher in the allocated RELEASE task with its task ID and owner. Open Developer Studio in a safe application preview, connect the companion origin, and approve the connection in its localhost popup. The private launcher URL stays in that popup. Releases → Check approved revisions discovers all registered categories; unfinished or unapproved tasks are excluded with reasons. Select eligible revisions and Prepare Release. Each operation requires confirmation on the local device. Review, Approve and Simulate additionally require the exact SHA prefixed by REVIEW, APPROVE or SIMULATE. Real Publish has no enabled execution path.

The companion checks task ownership, native worktree identity, branch, clean source, current commit, passing evidence and owner-approved task status. It revalidates selected tasks before review, approval and simulation. Candidate updates use the Studio lock, atomic JSON writes and version checks. A chained audit history records actions. This protects against accidental corruption and stale clients; a Windows account capable of editing the source/registry remains trusted, not a separate adversarial security boundary.

## Immutable candidates without unauthorized Git writes

Candidates compose read-only Git objects from the approved integration base and selected committed tasks. Uncommitted source is never exported. Independent file changes combine; unequal overlapping file changes block for manual resolution. Symlinks, submodules, sensitive paths, excessive objects and unrelated ancestry fail closed. A candidate is a locked Git-object composition and isolated Docker source bundle, not an additional host checkout.

If the resulting tree already equals an existing approved commit, that SHA identifies the candidate. A novel combination has a content fingerprint but **no candidate commit** and cannot be approved or simulated. Creating a real integration commit requires separate authorization and a future supported candidate-finalization procedure. This build never commits, merges, pushes or rewrites a worktree.

## Checks and previews

Focused source checks cover changed Python syntax, sensitive paths and secret patterns. Mandatory Docker probes and synthetic startup/login are separate fingerprint-bound checks. This is a smoke gate, not a claim that all feature-specific tests or worker behavior have been exercised. Selected task test evidence is retained; broader combined tests must be specified for the actual release.

Combined previews export only approved Git objects through the existing sanitizer. The pinned runtime retains network=none, no host mounts or published ports, non-root, dropped capabilities, readonly root, seccomp, bounded tmpfs/resources and synthetic PostgreSQL. Native network, HTTP, database, email, credential discovery and descendant-process probes run before application source starts. Desktop/mobile images are returned on demand; application JavaScript remains inside the container. A task cannot run overlapping preview leases. Stop Preview before starting its editable working-draft preview.

The reviewed seccomp policy is now hashed after CRLF-to-LF normalization. Git had normalized the accepted policy without changing its JSON. Reviewed normalized SHA256: `4540a0c176f2bdd83936ef958c0b306dc6ab6ea4310608149d11ac0803c68022`. Changed policy content still fails closed.

If a companion process is forcibly terminated, its lease may remain. Do not steal it or delete arbitrary containers: verify the owning process ended and the exact task/container labels and lease before owner-scoped recovery. Container lifetime remains bounded. Normal Stop/idle shutdown cleans up.

## Approval and mock executor

Review precedes approval; tests, ownership, exact SHA and candidate fingerprint must match. Final simulation confirmation is separate. The mock executor performs no network, subprocess or provider calls. It verifies GitHub revision plus all four canonical application/support service identities, matching revisions and health. Failure, revision mismatch and unhealthy outcomes are testable. Duplicate successful publication is blocked even after rerunning checks. Recovery requires a prior verified mock receipt and exact rollback confirmation; no guessed rollback SHA is accepted.

Migration and worker/deployment file changes block approval pending separate supported compatibility review. Migration review must identify the exact migration set, backward/forward compatibility, backup verification, restore rehearsal, recovery ownership and acceptable downtime. Code rollback cannot undo a database migration. Do not override these gates by editing registry JSON.

The mock branch is `main` solely as a test fixture, not verified production configuration. Canonical service IDs are topology references, not proof of current provider state.

## Phase 4C scope and launch prerequisites

Acceptance evidence is recorded outside source control in `.studio/phase4bc-acceptance.json`; previous Phase 3/4A acceptance is retained. Focused tests cover file restrictions, editor recovery/conflicts, owner routing, local pairing, candidate composition, eligibility, stale approvals, deployment failures and mock rollback. Browser checks cover the shipped panel and actual isolated application; localhost pairing does not establish hosted HTTPS compatibility.

Before first live launch: owner review and authorization to commit this implementation; an exact committed combined candidate; representative hosted HTTPS/browser pairing acceptance or approved local-only handoff; a separate trusted provider verifier/executor with least-privilege credentials stored outside the hosted app, durable execution/recovery locking and trusted audit storage; verified real production base/branch/service configuration and previous release; required CI and feature/worker compatibility tests; separate migration backup/recovery approval where applicable; fresh owner authorization for the exact GitHub/Render revision. Actual publishing remains disabled until that work is separately implemented and approved.

No new dependencies, polling loop, background watcher or ordinary application startup imports are added. The editor remains lazy and unchanged. Release catalog scans occur only when requested or after an operation. The companion and Docker previews run locally on demand.
