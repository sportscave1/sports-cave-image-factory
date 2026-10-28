# Authorised app and companion release — 2026-10-26

User authorised Git/Render release and companion update in the Orders/PSD repair chat.
Release task: 20261025-56edc5b8; owner codex-release-20261026-01a1746c.
Base: origin/main 166683874fca7d5332b3d9bd0f6ca366edc8f8dc.

Orders now requests and displays the latest 75 orders. Layout, filters, sorting,
controls and loading behaviour remain unchanged. The bounded backend reader accepts
75; the regression exercises 75 distinct orders and 150 line rows without a 50 cap.
Runtime change: orders_page.py. Regression updates: test_orders_bounded_reader.py,
test_orders_loading_ui.py, test_orders_prodigi_loading_repair.py.

Focused checks: 52 passed, 7 skipped, 5 subtests passed (Orders, preparation host,
companion Phase 5/provider identity, toolbar launcher and product recorder identity).
Broader Orders/UI selection: 139 passed, 13 failed; unchanged main: 138 passed,
the same 13 failures. No new failure. Topology and git whitespace checks passed.

Release uses the existing primary, webhook and SEO worker. Keep the existing SEO
cron suspended. No Blueprint sync, resource recreation or feature-flag activation.
After Render is live, install the exact release tree in a new immutable companion
runtime directory, gracefully stop only when idle, preserve task identity/settings,
source approvals, journals, receipts and previous installed release for rollback.

Scope exclusions: unfinished Windows recorder reliability acceptance/candidate,
ongoing mailbox connectivity diagnosis, unvalidated production-readiness tracking,
and historical dirty worktree snapshots. These are preserved in their original
worktrees; this release does not claim all outstanding development is complete.
Operational PSD files and customer-specific investigation evidence remain local.

Deployment IDs, runtime verification and preservation evidence are recorded locally
under output/release-20261026. Queue acceptance is not evidence of completed output.
