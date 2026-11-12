# Meta integration and release checks — 6 November 2026

## Candidate

HEAD remains e233171d01b7d8a28412a42e8e6a5f3c98e2c354, based on
64ed998a7e5f26fefd2d559fc2d7bb1873e24832. This follow-up is an **uncommitted
patch**, not a new candidate SHA. No push, deployment, production restart,
restore, settings change, resync, canary or AI activation occurred.

Task 20261106-source-repair, owner codex-source-release-20261106.
Only app.py, ads_meta_review_page.py, tests/test_meta_saved_performance.py and
this evidence document changed. Original AI worktree remains untouched.

## Reachable reporting repair

The existing authenticated Ads → Meta Review route now supplies a fresh account
authorization callback. Its Saved daily performance expander invokes the
existing sync_reporting service only on an explicit Sync saved performance
click. Permission is rechecked before provider/storage I/O; invalid day counts
fail before I/O. The existing live Refresh From Meta remains separate.

The existing service bounds the request to 1–31 completed account-calendar days,
validates account/currency/timezone and complete pagination, and commits through
the existing atomic sync store. UI shows period, currency, timezone, capture time
and attribution limitations. Errors are sanitized; prior success is labelled
as the last successful save. No scheduler, AI module, migration or dependency added.

## Focused evidence

- 28 tests passed on Python 3.14 and Python 3.12.15: six new reachable-control
  tests plus 22 source-repair tests. Permission denial/revocation, explicit-only
  execution, invalid ranges, unavailable configuration, reopen without sync,
  failure/recovery, account dates/DST, atomic failures and repeat safety covered.
- All 11 existing Meta LivePageTests passed on Python 3.14.
- Final six UI tests passed again on Python 3.12 after copy-only clarification.
- git diff --check passed. Prior combined 245 passes / 34 existing skips on
  both Python versions reused for unchanged release code.

Logs outside Git:
C:/Dev/SportsCaveWorktrees/source-repair-release-studio/.studio/runtime/20261106-source-repair/
meta-reachable-tests.log, meta-python312-tests.log, meta-existing-ui-tests.log.

Full-app browser: real router/account system with synthetic-only PostgreSQL
database release_smoke_full_e233171d. External preview fixture replaces only
Meta provider GET responses; no real credentials, internal Docker network
blocks application egress, both AI flags are 0. No fixture code ships.

Edge: Ads navigation, Meta Review live synthetic campaign, reachable completed-day
control and two manual saves passed. Provider fixture/source and stored row
reconcile: account 123, 2026-11-05, Australia/Sydney, AUD20 spend, 2 purchases,
AUD100 Meta-attributed value. Repeat save leaves exactly one daily row and two
successful sync logs. Navigation/reopen before the second click left one log.
No real-business reconciliation is claimed.

Orders: Edge displayed an orders_page.orders_viewport component-loading warning
even after reload; server served its unchanged inline HTML successfully and
returned correct search records. Fresh in-app browser session passed login,
both synthetic Orders rows and search filtering to SYNTHETIC-001. This isolates
a browser-specific symptom, not its root cause. No unrelated Orders code edited.
Prior Home smoke reused. Minor reporting caption clarification followed the
browser run and was covered by the final six tests.

## Production identity, health and backups — read-only

Primary Render Shell parsed only the current DATABASE_URL hostname/project
reference in memory. No secret output or export, no application import or DB write.
Actual primary OS ledger: **ceyzbfpuwuuxaiqwiltz** (sportscave1's Project).
The similarly named **sports-cave-image-factory**, eupachxkkbghjuuzlobz,
is a different Supabase project; its backup cannot substitute for ledger coverage.

Both projects currently report ACTIVE_HEALTHY via Management API.
For eupachxkkbghjuuzlobz, dashboard shows Healthy, no health advisor findings,
CPU2%, disk14%, RAM51%, 6/60 connections at observation. Last-24-hour logs:
seven gateway responses HTTP200, Storage/Realtime info entries; PostgREST
recorded "Warp server error: Thread killed by timeout manager" at
2026-11-05T18:39:12.225732Z. Successful PostgreSQL connections and schema-cache
reloads followed at Nov6 03:32Z; Realtime health HTTP200 at 03:32 and 03:35Z.
Database checkpoint logs include a client connection reset at Nov5 15:13:50Z.
The historical PostgREST timeout identifies an affected component in logs,
but does NOT prove the cause of the user's earlier Unhealthy badge. No current
unhealthy component reproduced; precise incident attribution remains unconfirmed.
No operator repair/restart was performed.

Authenticated dashboard confirmed seven COMPLETED physical backups for each:
- Actual OS ledger ceyzbfpuwuuxaiqwiltz: latest 2026-11-05T17:23:55Z =
  6 November 04:23:55 AEDT. Daily points 30 October–5 November UTC.
- Image-factory eupachxkkbghjuuzlobz: latest 2026-11-05T15:16:51Z =
  6 November 02:16:51 AEDT. Daily points 30 October–5 November UTC.

PITR is not enabled (add-on prompt, not changed). Backups do not include
Storage objects. No restore was attempted. Backup inventory is not a recovery
rehearsal; approval for a secured target/live-data handling/costs or explicit
owner acceptance of the untested recovery/data-loss risk remains necessary.

Existing role evidence for primary/worker reused: postgres, non-superuser,
BYPASSRLS, required table DML/schema/sequence privileges verified SELECT-only.
Webhook exact database identity/role remains unverified: free service lacks
Shell/SSH and connector has no remote execution. Needs a trusted existing
diagnostic path or owner-verified service role, without credential export.

## Production base, deployment and rollback gates

Read-only Render latest-deploy checks still show all three services live at
64ed998a7e5f26fefd2d559fc2d7bb1873e24832; production base has not changed.
No integration rebase required on that evidence. Recheck before release.

Conditional order after explicit release approval:
1. sports-cave-os-webhooks (srv-d9146onlk1mc739nrm7g): repaired active Shopify
   writer first; existing python webhook_server.py, /healthz HTTP200,
   receiver readiness and ordinary-cycle logs. No forced sync/webhook.
2. sports-cave-seo-worker (srv-d9ujm9navr4c73amurgg): existing
   python sports_cave_worker.py, supervisor/child startup and heartbeat logs.
3. sports-cave-os (srv-d8kl4on7f7vs73dvavv0): existing
   python sports_cave_server.py and existing predeploy command;
   /_stcore/health HTTP200, login/Orders/Meta navigation. No sync click.

No additional hosting service, paid add-on or migration required. Coordinate
existing main auto-deploy settings under separate approval before a push.
SEO daily cron stays suspended; AI and live-write automation stay disabled.

Rollback reference SHA for all three: 64ed998a7e5f26fefd2d559fc2d7bb1873e24832.
Artifacts: primary dep-dbmegs95efls73e3trrg;
webhook dep-dblcdgm7bikc73ah4l1g; worker dep-dblcdgm7bikc73ah4kjg.
Old webhook writer can erase repaired financial fields: keep the repaired writer
while reverting UI/worker, or separately approve coordinated writer suspension
and fallback. Never blindly restore old writer/database over later changes.
Canary field rollback requires exact audit/after-image reconciliation and its
own approval. No financial canary approval is implied by a source release.

**NO-GO for deployment.** Local Meta blocker fixed; remaining gates:
- Review and explicitly authorize commit of this patch; no new SHA exists.
- Verify webhook role/identity and resolve recovery rehearsal/risk acceptance.
- Retain Edge Orders component limitation; investigate before claiming full
  cross-browser acceptance.
- Approve actual final SHA, push/deploy sequence and rollback window separately.
- Later, separately approve bounded production source canaries and reconciliation.
