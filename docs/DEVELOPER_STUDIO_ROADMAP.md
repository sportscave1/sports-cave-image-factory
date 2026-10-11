# Developer Studio Master Plan V2 roadmap

| Phase | Deliverable | Gate |
|---|---|---|
| 1 — Worktrees and Engineering Foundation | Nine categories, short-lived task worktrees, routing, registry, VS Code/PowerShell launchers, focused checks | Original preserved; isolation verified |
| 2 — Local Previews | On-demand isolated servers/ports/test data, draft-aware previews, responsive tests | Provider writes denied and data/credentials isolated |
| 3 — Visual and Code Editor | Text/style/layout editing, authorized HTML/CSS/source edits, Save Draft, undo and history | Only assigned draft edited; revisions recoverable |
| 4 — Live / Draft / Preview / Publish | Dashboard, immutable candidates, CI, owner-approved exact-SHA GitHub/Render publishing, health checks/history | Combined tests and owner approval |
| 5 — VA Security | Assignments, individual identity, scoped repository access, reviews, protected publishing, audits | Access boundaries tested |
| 6 — Performance and Reliability | Lazy loading, minimal overhead, feature flags, recovery, monitoring and rollback | Measured impact and tested safe recovery |

Only Phase 1 is implemented. No UI, preview service, editor or publishing engine.

## Future version-locked Draft Registry

Draft fields: immutable UUID, display label (e.g. Draft V12), category, task ID,
assigned branch/worktree, base/current commit, editing status, preview config,
test results, review status and release eligibility. Labels are not identities;
persist UUID mappings and never reuse IDs.

Mutable drafts include dirty state and content fingerprints, because current
commit alone does not describe uncommitted files. Codex resolves a requested
draft UUID to its one assigned task/worktree and verifies both before editing.
Ambiguous labels require confirmation.

An approved release revision is a separate immutable record: release UUID, draft
UUIDs, full exact commit, test fingerprint, approval identity/time, combined
preview evidence, deployment IDs and health results. Any edit/new commit
invalidates old eligibility. Never label changing work an immutable release.
Retain feature worktrees until explicit cleanup; new tasks use updated approved code.

The Phase 1 registry supplies task identity, ownership, worktree, commits, status,
test snapshots and disabled preview metadata. Future drafts reference tasks
instead of creating nine independently diverging applications.
