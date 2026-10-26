# Mailbox release — task 20261025-35ed7e58

Owner explicitly authorised committing/pushing the mailbox changes and releasing them to GitHub/Render on 27 October 2026. No test-send address has yet been approved; a single request for an owner-controlled address, send permission and destination-inbox verification access is pending. Release authorisation does not establish approval for customer test emails.

## Scope and preparation

Canonical target: existing `sports-cave-os`, `srv-d8kl4on7f7vs73dvavv0`, Nathan workspace `tea-cut91gtsvqrc73e5acs0`. It hosts Email UI and the IDLE/index/outbox lifecycle. Do not deploy the separate CRM supervisor, webhook receiver or cron service for this mailbox change. Do not sync a Blueprint or alter service/network configuration.

Confirmed live/remote-main parent: `5980a803e5c0073f2e430b7d8e495e10c9b7d78d`, Render deploy `dep-dbf80g2jnfac73egeskg`. Mailbox-only patch applies cleanly to this parent. No migrations or dependency changes. Preserve task base/history and all existing work; integrate released main into this task branch after committing only task-owned mailbox files/evidence. Verify the final diff against remote main contains only mailbox files, tests and evidence. Never reset or overwrite another checkout. Recheck remote main before the push and use an ordinary fast-forward push (no force).

Release commit message includes `[skip render]` to suppress broad repository auto-deploys. After confirming no automatic deploy is running, manually deploy only the primary service through the existing Render workflow. This avoids restarting services that do not host changed mailbox code. Verify the specific new deploy ID reaches `live` and its commit is the approved release commit.

## Changes and verification

Seven production files: email component readiness/status, durable acceptance/reconciliation, dead-worker restart, partial-header cursor safety, health freshness/diagnosis, SMTP diagnostics, and bounded IPv6 attempts that reserve IPv4 time without hard-coded IPs or weakened TLS. Existing bodies, attachments, sanitisation, reply workflow and layout retained.

The component's initial ready message is now retried at most 20 times at 500 ms, stopping on the first host render or page exit. The live UI timeout was observed while static assets returned 200 and authenticated provider/index reads worked. A lost ready handshake is a tested failure mode; it is not yet proven to explain every live component timeout. Verify the actual deployed component before declaring this resolved.

Final checks: actual component in Chromium with a deliberately delayed (800 ms) parent listener rendered the workspace, received one ready message, stopped retries and had no page errors. Focused handshake unit checks, scheduler/context checks (73 assertions), reader sandbox checks, three existing transport tests and all 38 SQL/recovery tests passed. SQL uses disposable PGlite; a real local PostgreSQL server was unavailable (Docker daemon not running, no PostgreSQL service/binaries found), so full competing-process PostgreSQL locking remains unverified. Prior broad regressions remain recorded; no repeated speed benchmark was run. Render topology validator and diff whitespace checks passed.

## Post-release checks

1. Verify runtime commit and authenticated IMAP using existing credentials solely inside Render. Compare the latest 20 provider Message-IDs to the OS index; observe last-success time advancing without manual refresh. Read-only header fetches use EXAMINE/BODY.PEEK, no bodies or mailbox writes.
2. Check Inbox/Sent/Drafts counts and active durable drafts against the captured baseline, allowing independent owner activity. Never clear queues, reset cursors, delete drafts or resubmit ambiguous sends.
3. Confirm Email component renders on a normal authenticated page, and measure actual opening/expansion where accessible. Keep remote images blocked and load only one initial body.
4. Exact October 7 Message-ID search in provider Sent returned no matches on 26 October. This is insufficient to prove failure or delivery: preserve unknown status and do not resend. Inspect the post-release receipt without modifying it.
5. With an approved test address, execute the real inbound/outbound/reply/attachment round trip and verify destination receipt separately from SMTP acceptance. Observe at least 30 minutes through the previous approximately 20-minute IDLE interval, using read-only provider/index comparisons and logs. No fully-working claim before both authenticated live sync and real round trip pass.

## Rollback

Rollback target is the retained primary build `dep-dbf80g2jnfac73egeskg` / commit `5980a803e5c0073f2e430b7d8e495e10c9b7d78d`. Use the primary service's existing Render rollback action if the new build fails readiness or introduces a material regression (authentication/index failure despite provider availability, broken component or reply/attachment behavior, or duplicate submission risk). Keep the current service identity and configuration. No database rollback is needed: schema is unchanged, existing receipt statuses/copy fields remain compatible. Runtime rollback does not reverse already accepted emails or database receipt updates. Never resend to compensate.

If the retained build is unavailable, prepare a mailbox-only revert commit on current remote main, review its exact diff, use `[skip render]`, push normally and manually redeploy the primary. Do not reset remote history or revert unrelated releases. Record final deployed commit, deploy ID, verification evidence and any remaining blockers.
