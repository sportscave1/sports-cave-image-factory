# Review against latest released code — 26 October 2026

Task: `20261025-35ed7e58`; owner: `codex-mailbox-reliability-01a157b1-20261026`. Reverified the existing isolated worktree, branch and registry owner before changes. All previous implementation and evidence retained; original EMAIL category changes remain untouched.

## Released baseline and compatibility

Read-only Render metadata for the canonical primary `sports-cave-os` (`srv-d8kl4on7f7vs73dvavv0`) in the previously user-confirmed Nathan workspace reports:

- Live commit: `5980a803e5c0073f2e430b7d8e495e10c9b7d78d`.
- Live deploy: `dep-dbf80g2jnfac73egeskg`, finished `2026-10-25T22:22:05.203103Z`.
- Task base remains `6e2805d058713cc64cfa70e7a85ee23ea66db7e1`; no branch movement, merge or commit.

The released email source, component, email tests, migrations and requirements are unchanged from the task base. Reviewed the shared `app.py` navigation changes: the released edits retain prepared Product Uploads state; they do not alter email routing or its worker/controller contracts. Other released changes concern unrelated application modules. There are no overlapping released edits in the task's changed files.

Exported released Python sources, email component, shared top-bar and branding assets, and email migrations into an ignored integration fixture inside this task worktree (`.tmp-mailbox-release-review`). `git apply --check` succeeded for the entire tracked task patch, which was then applied only in that fixture. Added the task's new test sources and ran the focused regressions there. This verifies release-plus-task compatibility without moving/resetting the existing worktree or touching another task. The fixture contains no production credentials/customer data and is retained locally.

## Finding fixed locally

The acceptance-recovery implementation called `_remember_acceptance` from the SMTP 100% progress hook and called it again after the provider returned accepted. This issued two receipt-persistence attempts for the same observed SMTP 250. A transient failure of the redundant second write recreated an in-memory pending receipt and falsely reported storage recovery even though the first write had already succeeded.

`support_email_durable.py` now retains the hook's captured evidence and skips the redundant persistence attempt. Providers that return accepted without invoking the progress hook still use the normal fallback persistence path. The genuine database-outage buffer and worker flush remain unchanged; ambiguous submissions are never blindly retried.

Added `test_progress_acceptance_is_persisted_once_without_false_recovery_warning` in `tests/test_mailbox_reliability_recovery.py`. Before the fix, it failed with two persistence calls (expected one) and reproduced the false recovery condition. After the fix, the receipt is accepted, persisted once, has no pending-storage warning, and retains its stored acceptance timestamp. Existing outage/restart tests also pass.

No other regression or integration conflict was found in the reviewed paths. This is a focused email review, not a full regression test of unrelated released application modules.

## Final verification

- Task worktree: 36 disposable SQL/recovery tests passed (including the new regression).
- Released source plus task patch: 296 focused Python tests completed, 288 passed and eight existing SQL-dependent checks skipped.
- Released source plus task patch: all 36 separate durable SQL/recovery tests passed using disposable loopback PGlite and fabricated IMAP/SMTP.
- Released source plus task patch: five Node component suites passed, including 73 scheduler/context/menu assertions and 20 bounded-cache/helper assertions. Connection status, send-state semantics and reader sandbox checks passed.
- Changed Python syntax, component JavaScript syntax and `git diff --check` passed.

The first temporary integration export omitted the released signature-logo asset, causing FileNotFoundError-related Python failures; a subsequent component run found the omitted top-bar HTML. These were fixture omissions, corrected by exporting those exact released assets. All final checks above passed without product changes to those assets. Existing original performance measurements and Chromium evidence remain in `REPORT.md`; they were not re-measured for this small persistence fix.

Production connectivity, exact provider Sent evidence for the October 7 unknown operation, and actual sandbox sending remain unverified as described in `REPORT.md`. SQL tests use the existing PGlite fixture rather than a live PostgreSQL service; full database concurrency fidelity and live provider behavior remain limitations. No new production access or mailbox mutations were needed for this review.

Status: local review and fix complete, uncommitted; no push, merge or deploy. Live mailbox remains unpatched until an authorised release.
