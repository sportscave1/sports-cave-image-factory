# Repository operating rules

## Production Render topology — do not duplicate

The only canonical primary web service is `sports-cave-os`
(`srv-d8kl4on7f7vs73dvavv0`). Exactly one primary Sports Cave OS web service is
allowed. Never delete, replace, rename, or recreate it to change application
branding.

The services `sports-cave-os-webhooks`, `sports-cave-seo-worker`, and
`sports-cave-seo-daily-sync` are intentional supporting services. Never create
another primary service. Never change the primary identity in `render.yaml`
without first checking [docs/RENDER_SERVICE_TOPOLOGY.md](docs/RENDER_SERVICE_TOPOLOGY.md).
Always run `python scripts/validate_render_topology.py` and inspect a Blueprint
preview before syncing. A preview that creates another primary application must
not be applied.

## Permanent local-only development mode

Development is local-only by default. Do not commit, push, merge, deploy or
mutate production without explicit user authorization for that action. The
October 10 consolidated deployment is a one-release exception only. After that
release, local-only mode remains in force; future releases require fresh explicit
authorization.

## Developer Studio task isolation

- Before editing, verify git rev-parse --show-toplevel, git branch --show-current
  and assigned task ID/owner. Work only in that task's worktree.
- Category folders are idle entry points. For a new task, run
  scripts/studio/Studio.ps1 New -Description "<task>" -Owner "<unique-session>".
  Use its separate worktree; never silently move an existing session.
- Preserve unrelated/unfinished work. Never edit another task's folder or silently
  discard, reset, stash, overwrite or clean another task's changes.
- Keep changes focused; necessary cross-module changes belong in the same task
  branch. Avoid unnecessary refactoring.
- Run focused tests, fix new failures and record task status/results with Studio.
  Report readiness accurately; a clean worktree does not prove completion.
- Retain task branches/worktrees for review. Commits require explicit authorization.
  Never automatically push, merge into production or deploy.
- Never use production credentials/live customer data in development previews.
  Never send real email, publish Meta ads, change live Shopify/Edition Ops or
  activate customer automations during testing. Preview is disabled in Phase 1.
- See docs/DEVELOPER_STUDIO.md for procedures and
  docs/DEVELOPER_STUDIO_PREVIEW_SAFETY.md for Phase 2 prerequisites.
