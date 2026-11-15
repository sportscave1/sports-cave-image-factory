# Sports Cave OS Developer Studio — Phase 1 V2

Local engineering infrastructure only. No production configuration, application
behavior, GitHub rules, account settings or deployment tooling is changed.

## Start here

From any PowerShell directory:

~~~powershell
$studio = 'C:\Dev\SportsCaveWorktrees\Studio.ps1'
& $studio New -Description 'Meta Ads posting popup' -Owner 'your-name/chat-unique-id' -Open
& $studio New -Description 'Meta Ads creative refresh' -Owner 'your-name/another-chat-id' -Open
& $studio List
& $studio Categories
& $studio Open -Id '<returned-task-id>' -Owner '<same-owner>' -Open
~~~

Every New allocates a separate native Git worktree and branch. Two ADS tasks get
different folders. Branches use codex/task/category-description-unique-id.
Duplicate IDs, duplicate unfinished names, wrong owners and unknown workspace
identities are rejected. Supply -Category for deliberate cross-module work.
Ambiguous descriptions prompt; -NonInteractive fails safely without allocating.

Start a new Codex conversation in the returned folder, or use:

~~~powershell
codex --cd '<returned-worktree-path>'
~~~

The installed CLI supports --cd; the VS Code extension works in its opened
workspace. Official context: https://learn.chatgpt.com/docs/projects
(Codex project/workspace section). The launcher does not relocate an existing
conversation, change models or intercept every chat in the desktop app.
Chats started in the original folder remain there. Use the launcher before new
development. The original folder's AGENTS.md deliberately remains untouched.

Generated .code-workspace files live outside Git in .studio/workspaces. Their
window titles include task ID and branch. VS Code opens a new window.
Alternatively: code --new-window '<worktree-path>'.
There are no automatic startup hooks or background services.

## Category entry points

All paths are beneath C:\Dev\SportsCaveWorktrees.

| Category | Folder | Branch | Scope |
|---|---|---|---|
| ADS | sports-cave-ads | codex/category/ads | Ads, Posting, Instant Experience, Carousel, Creative Refresh, Meta Review |
| EMAIL | sports-cave-email | codex/category/email | Email, CRM, campaigns, subscribers, templates, flows, segments, automations |
| PRODUCTS | sports-cave-products | codex/category/products | Upload, Management, tagging, Mockups, Design Studio, imagery/descriptions |
| EDITIONS | sports-cave-editions | codex/category/editions | Edition Ops, allocation, numbering, certificates, inventory, overrides |
| CORE | sports-cave-core | codex/category/core | Home, navigation, shared UI, performance, responsive design, protection, access/security |
| INTEGRATIONS | sports-cave-integrations | codex/category/integrations | Shared APIs, Analytics, Reporting, backend, cross-system synchronization |
| COMMERCE | sports-cave-commerce | codex/category/commerce | Orders, Fulfilment, returns, refunds, customer order workflows |
| GROWTH | sports-cave-growth | codex/category/growth | Social Media, Social Inbox, SEO, Reviews, organic marketing |
| RELEASE | sports-cave-release | codex/category/release | Approved integration, combined testing, release candidates/readiness |

Category worktrees are idle entry points. Never accumulate unrelated tasks there.
RELEASE is for approved integration, not ordinary features. Category starting
revisions are recorded in .studio/registry.json; they are never silently reset.
Categories reports stale bases. New tasks use the current explicitly approved
registry commit, not the category branch, main, origin/main or guessed HEAD.

## Authority and integration

Read-only Render verification on 11 October 2026 confirmed canonical sports-cave-os
(srv-d8kl4on7f7vs73dvavv0), branch main, autoDeploy=yes, live deploy
dep-db5gi3gu01pc73el97gg at 7a6248355d73dfca70318fb9028212c3ba8708d5.
This matches the local Inbox release report. Original local main was still
2af257694032fb6a9aaaca4ebced7c364d4440d7; unfinished work is not assumed live.

Setup starts from that exact live commit. The user authorized only isolated
infrastructure commits. The tested setup revision becomes the initial approved
development base; it is not deployed. Original uncommitted files are excluded.
Record dependencies on unfinished original code in task evidence/history; do
not silently copy it. An explicitly reviewed transfer/integration is required.

Production main auto-deploys. Never integrate unapproved features there.
Prefer small tasks and frequent reviewed integration in isolated release
candidates. Resolve shared-code conflicts explicitly; never silently discard a
side. Test combined changes and do not bypass checks. After owner approval:

~~~powershell
& $studio ApproveBase -Base '<full-40-character-commit>' -Owner '<owner>' -Evidence '<approval and combined-test evidence>'
~~~

This only updates the local base pointer/history, never existing worktrees.
The commit must contain Studio tooling. Newer does not automatically mean approved.

Future release:
Task → focused tests → review → approved integration → combined preview → CI →
owner approval → exact tested commit → GitHub → existing Render app/workers →
live health verification. Existing manual PowerShell deployment commands remain
intact but require separate explicit release authorization. Never publish mutable
uncommitted working-directory contents.

## Completion and evidence

~~~powershell
& $studio Status -Id '<id>' -Owner '<owner>' -Status 'Implemented Locally'
# Run relevant offline tests and fix new failures.
# With explicit commit authorization, in the assigned task folder only:
git status --short
git add -- <only-explicit-reviewed-task-files>
git commit -m '<focused task description>'
# Re-run relevant checks for the exact committed revision, then:
& $studio Verify -Id '<id>' -Owner '<owner>'
& $studio RecordTests -Id '<id>' -Owner '<owner>' -Result passed -Evidence '<exact focused commands, results, log location>'
& $studio Status -Id '<id>' -Owner '<owner>' -Status 'Tested'
& $studio Status -Id '<id>' -Owner '<owner>' -Status 'Ready for Review'
~~~

A clean worktree never means completed automatically. Verify runs static and
infrastructure checks, not all feature tests. RecordTests is an explicit
human/agent attestation of tests actually run, bound to commit and file snapshot.
Review readiness requires both current passing evidence and a clean committed
worktree. List invalidates displayed readiness after changes; reverify/retest.
Ready for Review is not approval. Approved, Integrated and Released require
evidence and record external decisions; they never execute those actions.
Retain branches/worktrees until integrated or explicitly authorized cleanup.
There is no automatic delete, force, reset, stash, commit or cleanup command.

## Registry and recovery

Runtime state: C:\Dev\SportsCaveWorktrees\.studio\registry.json, never committed.
Schema 1 stores ID, name, category, path, branch, base/current commit, owner,
status, timestamps, tests/verification snapshots, readiness, history, dependency
placeholders, ownership and disabled preview configuration.

States: Planned, In Progress, Implemented Locally, Tested, Ready for Review,
Approved, Integrated, Released, Blocked.

An exclusive registry.lock stores PID/time. Writes use a same-directory temporary
file, fsync and atomic replacement. Allocation reserves identity before Git writes.
On failure it retains any branch/folder and marks the task Blocked. Category
reservations likewise fail closed. Never automatically clear locks, expire
ownership, adopt unknown folders or retry by overwriting them.
Confirm the process stopped and consult the owner before manual lock recovery.
If Git succeeded but registration/opening failed, inspect registry and git worktree
list and reconcile explicitly. Open verifies root, shared Git directory, branch
and owner. Ownership is cooperative protection, not an access-control boundary
against manual JSON/filesystem edits. Use a unique Owner per active Codex session.
Never run two active sessions in one task workspace.

## Focused validation

Python requirements/unittest, individual Node tests and extension package scripts
exist; no root JavaScript package or pyproject was found. Python 3.14 and Node 24
are installed; existing release CI selects Python 3.12.8. Use a compatible Python
environment for application tests. Studio installs no dependencies.

- Infrastructure: python -B scripts/studio/test_studio.py
- Syntax: Verify parses changed Python with ast, without importing the application.
- Python features: python -m unittest tests.<relevant_module>; review fixtures first.
- Frontend: node tests/<relevant_component>.cjs or node --test <focused-test.mjs>.
- Extension: npm --prefix shopify_customer_account run test:pixel / test:vault.
  These are tests, not Shopify dev/deploy commands.
- Topology: python scripts/validate_render_topology.py, read-only.
- Worker compatibility: syntax-check changed app/worker modules and run relevant
  mocked contracts together, including webhook dependencies.
- General application startup/import: blocked until Phase 2 isolation exists.
  Importing sports_cave_server is not a harmless smoke test.
- Secrets: Verify scans changed files for sensitive filenames and common key/
  private-key patterns, withholding values. This is a heuristic, not a full audit;
  unusual secrets and large/binary artifacts still need review.
- Release: git status --porcelain empty; git rev-parse HEAD equals the exact tested
  and approved SHA. Verify app/worker revisions together after future authorized release.

Future mandatory CI: focused Python/Node contracts, safe syntax/import smoke tests,
secret scanning, topology invariants, worker compatibility, combined release
checks and exact artifact SHA. No CI or branch protection is changed in Phase 1.
