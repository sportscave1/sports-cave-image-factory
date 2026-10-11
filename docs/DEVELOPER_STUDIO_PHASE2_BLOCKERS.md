# Phase 2 safety preflight — blocked, not verified

11 October 2026, Australia/Sydney.

## Assigned workspace

- Task: 20261011-c24ca137
- Owner: me/phase2
- Category: CORE
- Branch: codex/task/core-developer-studio-phase-2-local-previews-an-20261011-c24ca137
- Base/current commit: 2a0bf7b78067adfc0b359b4e364b0f7afac6241f
- Worktree: C:/Dev/SportsCaveWorktrees/sports-cave-core-developer-studio-phase-2-local-previews-an-20261011-c24ca137

The registry, Git root and branch agree. The assigned worktree was clean before
this report. The chat default directory still points at the original repository;
all task commands explicitly target the allocated worktree. No original files
were edited. Phase 1 source and its approved base remain unchanged.

## Critical blocker

Full-application preview isolation is not verified. Per the user's explicit
fail-closed/stop requirement, no production application process or preview was
started. Phase 2 is NOT implemented or verified by this preflight.

Evidence from focused source inspection:

- app.py imports application modules and calls load_dotenv(). Removing inherited
  environment variables alone does not establish credential isolation.
- sports_cave_server.py imports application routes, wraps the app in IdleLifecycle,
  and runs deployment migrations when RENDER or a database URL is present. It also
  calls prepare_google_seo_storage(), which can migrate and enqueue repairs.
- supabase_backend.py uses psycopg connections. A localhost HTTP listener does not
  constrain its database destination or provider writes.
- tests/fixtures/email_v2d_preview.py patches Email-specific providers/storage and
  selected SMTP/IMAP entry points. Those patches are not an application-wide
  Shopify/Meta/Resend/database/worker safety boundary.
- Existing account tests use a separately supplied LOCAL_ACCOUNT_TEST_DSN and
  create a disposable PostgreSQL database. They do not establish isolation for
  an arbitrary running application draft.
- No Docker or Podman command was found. wsl --list --quiet reports WSL is not
  installed. WindowsSandbox.exe was not found by command discovery. No available
  isolated runtime was established by these checks.

A container is not intrinsically required, but an enforceable, tested isolation
boundary is. Provider-specific mocks alone must not be advertised as protection
against all external mutations in a changing application worktree.

## Required before preview acceptance

1. Select and provision a verifiable isolation boundary that prevents outbound
   production access and excludes host credentials/data. Installing/enabling a
   host virtualization runtime may require administrator access and a reboot;
   none was attempted during this preflight.
2. Provide synthetic application data and explicit mock adapters, with migrations,
   background workers, customer automations and unknown integrations denied.
3. Prove fail-closed behavior across database/native-client connections, HTTP,
   SMTP/IMAP, subprocesses, credential-file discovery and child jobs.
4. Only then demonstrate real application previews from two distinct task
   worktrees, independent ports/runtime/data, save/reopen ownership, recovery,
   responsive views and idle shutdown.

## Changes and verification

Only this report and the assigned task's runtime registry status/history were
changed. No draft UI, preview service or partial mock application was substituted.
No application source, deployment configuration or existing task was modified.
No dependencies installed; no commits, merges, pushes or deployments performed.

Checks performed: registry owner/category lookup, Git worktree/root/branch/clean
status, focused startup and fixture inspection, local runtime discovery.
No application, integration or browser tests were run; starting them without
established isolation would not satisfy the safety requirement. No performance
claim is made. No new server or background process is running.
