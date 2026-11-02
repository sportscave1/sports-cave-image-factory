# Approved mailbox-only release — 27 October 2026

Task20261025-35ed7e58, owner codex-mailbox-reliability-01a157b1-20261026; existing isolated worktree retained. Owner explicitly approved commit/push/deploy of the tested mailbox fix. Production source change: support_email_reads.py only. Three regression tests and the prior follow-up evidence accompany it. No infrastructure, configuration, schema, dependency or UI layout changes.

Commit **6661eb6bf3ea8bfe6762273245f57124e952e38f** pushed normally and atomically to main and the task branch. `[skip render]` suppressed repository-wide auto-deploys; only canonical primary sports-cave-os (`srv-d8kl4on7f7vs73dvavv0`) was manually deployed. Deploy **dep-dbfu801srm7s73buiqm0** became live **27October10:39:11 Sydney** (26October23:39:11.117324UTC), on new instance dd89r. Supporting services were not deployed.

The approved patch hash is unchanged from the74 passing focused tests (23 inbox/recovery plus51 connection/polling/IDLE). The new tests failed against the prior scheduling behavior and pass with the fix. Topology, diff/JSON checks and production-only rollback apply-check pass. No passing suites were unnecessarily repeated for release. Rollback is retained build05a0b87d, deploy dep-dbft45tg1s2s73es9390; a targeted source-only reverse patch is also prepared. Recheck current main before any rollback so later unrelated work is preserved.

## Actual verification

- Render reports the exact approved commit live. Public health endpoint returned200/`ok`, observed283.6ms from Windows.
- Authenticated watcher published a new fenced signal at10:41:21.226 Sydney. Index succeeded at10:41:24.905, **3.679s later**, UID122/94 messages. Further periodic index successes through10:44:45.678 (sampled10:45:16.493) confirm the loop continues without manual refresh. Watcher lease remains active.
- Prior rollout's recorded watcher signal→index success interval was67.511s. This rollout's interval is3.679s. These are single observations, not a repeated matched benchmark or a latency guarantee.
- Logs show old cx7fm process shutting down10:41:10.671 and finishing10:41:13.033, approximately two minutes after the traffic switch. New recorded index success was11.873s after old-process exit. Total traffic-switch→recorded index success remains133.788s; do not confuse the shorter coordination wait with Render's old-instance retirement time. Shared index updates continued during overlap. No lease-busy event was captured in available logs, so no claim that every historical second had this cause.
- October7 operation remains unknown, copy pending, **one submission attempt**; only automatic read-only reconciliation count advanced. It was never resent, reclassified or edited. Both previously approved round-trip receipts remain accepted/appended with one attempt each. No email was sent for this release.

Only metadata/status SELECT queries were used for the database checks; no frozen MIME or credentials were exported and no mailbox/draft/queue reset occurred. Detailed samples and deployment metadata: followup-release.json.

## Status and precise limits

**Release complete; authenticated sync and post-handover periodic progress verified.** The earlier live BYE recovery (21.161s to authenticated signal,24.870s to index success), real UI timings and approved real round trip are retained in the preceding evidence. No new BYE fault or email test was induced for this scheduling-only release. Matched throttled/long-thread UI byte comparisons and real PostgreSQL competing-worker tests remain unverified. The separate diagnostic browser tab was left onSlow4G when Computer Use stopped in the prior turn; no throttled result is claimed.
