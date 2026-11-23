# Edit Design workflow repair — 23 November 2026

Task/owner: `edit-design-workflow-repair-20261123` / Codex current chat.
Workspace: isolated managed worktree, branch `codex/edit-design-workflow-repair-20261123`.
Authorization: user requested diagnosis, minimal prompt strengthening, and push live to Git/Render.

## Evidence and cause

The latest relevant ChatGPT chat, **Edited PSD Verified**
(`6b035221-2194-83ec-98a1-6892189ccbc7`), reported that removing the score from
**Mikal Bridges — At the Buzzer** succeeded, but canonical replacement failed.
Its original and staged PSDs were approximately 250 and 264 MiB. The saved
prompt and response explicitly reported Design Studio's 150 MiB rejection.

`design_review_replace.apply` imposed that limit despite `upload_revision`
already using chunked Dropbox upload sessions. Review intake permits 1 GiB.
The edit prompt also inherited a new-design heading, mandatory generation and
research defaults, and wording discouraging local-only corrections, conflicting
with the user's instruction to remove only the score and preserve everything else.

## Focused changes

- Keep the shared creative stages; add edit-specific precedence, local correction
  scope, capability/size preflight, ordered closeout checkpoints and recovery.
- Require canonical PSD plus revision-bound JSON verification and temporary-file
  cleanup before completion. Staging alone remains incomplete.
- Match the existing 1 GiB intake limit using the existing chunked revision upload;
  retain hash, revision, collector-layer, rollback and cleanup guards.
- Download staging once when no legacy trial exists. Release the original parsed
  layer tree before inspecting the staged PSD to reduce memory use.
- Upgrade only unclaimed edit snapshots without changing the user brief, selected
  revision, queue identity or receipts. Already-running chats retain their sent prompt.

## Validation and limits

Focused offline tests cover edit prompts, replacement/rollback/cleanup, queued
prompt migration, Review gallery/title handling and Dropbox upload integration.
Large-file guard regression uses synthetic metadata at the reported sizes, with
small content fixtures; it is not a live 264 MiB PSD round trip.
Database-backed checks skip without their isolated test database.
Render topology validation remains required before release.

This release repairs future execution and available server replacement. It does
not itself apply the retained Mikal Bridges artwork or resume the old ChatGPT
chat. A prompt cannot guarantee completion during unavailable tools, lost access
or external failures; those must remain accurately reported as incomplete.
