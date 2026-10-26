# Mailbox release — task 20261025-35ed7e58

Owner explicitly authorised committing/pushing the mailbox changes and releasing them to GitHub/Render on 27 October 2026. In response to the bundled test-send/receipt-verification request, the owner approved hello@sportscaveshop.com. Two self-addressed test messages (initial with one small attachment, then reply) were sent and actual destination receipt verified. No customer test recipients were used.

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

Update after initial release: unrelated release `6e59900dff5e317bce2bb4c0bd84a88703b310f3` superseded the initial mailbox deploy and retains all its source unchanged. Do not roll back to the old 5980a803 build now: that would discard the intervening unrelated release. For the component-height follow-up, immediate rollback is the retained 6e59900d build `dep-dbfsf695efls738rdpag`; this preserves the earlier mailbox repair and unrelated changes. A full mailbox rollback must instead use a reviewed mailbox-only revert on current main. No schema/config rollback is required.

Subsequent unrelated live release `05a0b87d205a668ebe2508303ae797a9b804e639` / `dep-dbft45tg1s2s73es9390` at 22:23:01 UTC also preserves all mailbox source. Main `ca093ab4bdff7acacf60aec03720594f86fcd792` adds only test whitespace. Older build rollback now risks removing those unrelated changes. Prepared local `.tmp-mailbox-full-rollback-reviewed.patch` (SHA-256 `4cdbe4884ae7384f1cd50165825e6f3c677f7ae0e3e54cafeed2ac2081797ec0`), reverting only the seven mailbox production files to 5980a803 source. `git apply --check` passes against ca093ab4. It has not been applied. If needed, recheck against then-current main, apply/review only that mailbox patch, commit with `[skip render]`, push normally and manually redeploy only primary; preserve newer unrelated code. No schema reversal or resend is part of rollback.

Rollback target is the retained primary build `dep-dbf80g2jnfac73egeskg` / commit `5980a803e5c0073f2e430b7d8e495e10c9b7d78d`. Use the primary service's existing Render rollback action if the new build fails readiness or introduces a material regression (authentication/index failure despite provider availability, broken component or reply/attachment behavior, or duplicate submission risk). Keep the current service identity and configuration. No database rollback is needed: schema is unchanged, existing receipt statuses/copy fields remain compatible. Runtime rollback does not reverse already accepted emails or database receipt updates. Never resend to compensate.

If the retained build is unavailable, prepare a mailbox-only revert commit on current remote main, review its exact diff, use `[skip render]`, push normally and manually redeploy the primary. Do not reset remote history or revert unrelated releases. Record final deployed commit, deploy ID, verification evidence and any remaining blockers.

## Follow-up component-height regression

The owner confirms normal Email loads after the initial release. A stricter delayed-listener Chromium test nevertheless reproduced an independent edge case: content rendered inside a zero-height iframe because the host missed the first height announcement. On the first acknowledged host render, reset only the local height deduplication marker so normal render sends the current height again. Later renders retain height deduplication. No layout/body-loading behavior changes. Before fix, the new actual-frame-height assertion failed; after fix the frame is 710px, the workspace renders, retries stop, later height messages remain deduplicated, and no browser errors occur. The component also renders in a real local Streamlit host with fabricated data. Release this small follow-up only to the primary and restart the full live observation on its final instance.
