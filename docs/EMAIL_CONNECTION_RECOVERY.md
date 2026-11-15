# Email mailbox outage investigation — 27 September 2026

## Finding and remaining evidence gap

The production root cause is **not yet established**. The screenshot confirms that `Workspace.load()` received an error from folder discovery, but the old code replaces the underlying safe error with “Could not load folders. Check the mailbox connection.” A login, TCP/TLS, timeout, LIST or unexpected local error can all produce that screenshot. It does not establish incorrect credentials or a broken LIST parser.

Render's read-only deployment records confirm:

| Revision | Deployment completed (UTC) | Evidence |
| --- | --- | --- |
| `45807b7` | 2026-09-27 06:01:40 | Current live deployment; user reports mailbox failure here |
| `2bfd98e` | 2026-09-27 05:59:10 | Immediately preceding deployment |
| `c02c26b` | 2026-09-27 05:43:04 | Earlier composer-fix documentation commit |
| `b109bd5` | 2026-09-27 05:39:30 | Notification tests/fixture commit |
| `dc2db58` | 2026-09-27 05:34:01 | Notification implementation |
| `4ee3595` | 2026-09-27 05:03:51 | Signatures |
| `2e89925` | 2026-09-27 04:23:09 | Performance/layout |

The last *verified working mailbox* commit and first *causally broken* commit cannot be assigned from deployment status alone. `2bfd98e` is the previous deployment, not independently proven to have loaded email successfully. No rollback is justified by the available evidence.

The log endpoint refused access without a confirmed Render workspace. A read-only request for “Nathan's workspace” is pending with Nathan. No mailbox connection was attempted. Existing logs, if retained, may identify an exception type; the old provider does not log every failed IMAP response, so they may still be insufficient.

## Exact commit boundaries

`45807b7` changed only:

- `docs/FILES_LAUNCHER_DEPLOYMENT_FIX.md`
- `files_window_launcher.py`
- `tests/fixtures/email_notifications_preview.py`
- `tests/fixtures/files_launcher_preview.py`
- `tests/test_files_window_launcher.py`

Despite its combined deployment title, it contains no production Email provider/page/component change.

`2bfd98e` changed `app_search.py`, `components/sports_cave_top_bar/index.html`, `docs/GLOBAL_SEARCH_V2.md`, `tests/test_app_search.py`, `tests/test_app_search_component.cjs`, `tests/test_top_bar.py`, `top_bar.py` and `top_bar_api.py`. It contains no Email adapter change.

`c02c26b` contains only `docs/EMAIL_COMPOSER_FOCUS_FIX.md`. `b109bd5` contains only `tests/fixtures/email_notifications_preview.py`, `tests/test_composer_search_focus.cjs` and `tests/test_top_bar.py`.

The earlier notification commit `dc2db58` did include composer/focus changes alongside notifications. Its complete file list is: `components/sports_cave_top_bar/index.html`, `components/support_email/mail.js`, `docs/EMAIL_NOTIFICATIONS.md`, `docs/EMAIL_V1.md`, `support_email_notifications.py`, `support_email_page.py`, `support_email_provider.py`, `support_email_workspace.py`, `tests/fixtures/email_notification_runtime.py`, `tests/fixtures/email_notifications_preview.py`, `tests/profile_email_notifications.py`, `tests/test_email_notification_component.cjs`, `tests/test_support_email_notifications.py`, `top_bar.py`, and `top_bar_api.py`. Its provider changes add STATUS/notification methods; they do not edit configuration, connection lifecycle or LIST parsing.

An AST comparison confirmed that `load_configuration`, `_connection`, `discover_folders` and `parse_folders` are identical in commits `335c006`, `2e89925`, `4ee3595`, `dc2db58`, `2bfd98e` and `45807b7` before this repair. No accidental filename-pattern inclusion of a changed login/LIST implementation was found.

The working tree already contained the previous, uncommitted send-status and reply-default implementation when this task began. Those changes are preserved. HEAD stayed `45807b7` throughout this investigation; no concurrent commit was observed during this task.

## Connection, configuration and notification findings

- The existing variables remain supported: `SPORTSCAVE_EMAIL_IMAP_HOST`, `SPORTSCAVE_EMAIL_IMAP_PORT`, `SPORTSCAVE_EMAIL_IMAP_SSL`, `SPORTSCAVE_EMAIL_ADDRESS`, `SPORTSCAVE_EMAIL_PASSWORD`. No new variable or password rotation is needed for this patch. SMTP configuration remains separate.
- Raw IMAP connections are not cached in session state or shared between notifications and mailbox browsing. Every operation creates its own connection and logs out in `finally`, with shutdown fallback. Historical thread resolution only reuses a connection within one bounded operation.
- Notification STATUS checks use a separate provider/connection, a shorter timeout and existing bounded polling. The recovery patch does not add notification retries or change notification semantics. Source inspection and mocks show no shared socket being closed by notifications. Production connection limits or transient server failures cannot be ruled out without logs.
- Folder parsing, SPECIAL-USE mapping and wire names are unchanged. Successful folder metadata is cached for 300 seconds; bodies and thread membership retain their existing caches.
- The previous folder failure was retained for 20 seconds, not 300. It was an error entry, not a successful empty result, but the UI misleadingly displayed “0 conversations.” This is now corrected.

## Local repair implemented

1. Safe categorized provider failures distinguish not configured, authentication, timeout, TLS, DNS, folder listing, folder selection and temporary/unclassified service failures. Logs include controlled stage/category and exception class only; never raw responses, tracebacks, credentials or message content.
2. Folder discovery, Test Connection and header reads retry a transient failure once using a fresh connection. A failed LIST response can also retry once. Each attempt closes its own connection. Authentication rejection and TLS verification failure do not retry. No mailbox write, SMTP send or notification poll is replayed by this mechanism.
3. Test Connection still uses the same configuration, authenticates, selects INBOX read-only, lists folders and logs out.
4. Failed folder discovery is excluded from the successful folder cache. A separate five-second failure throttle prevents repeated reruns from hammering the server. Explicit Refresh bypasses that throttle and clears relevant mailbox state. Successful retry restores normal folders and headers.
5. The controller preserves safe provider diagnostics instead of overwriting them. Connection failure displays “Mailbox unavailable,” suppressing the false zero count and live-data footer. Genuine successful empty mailboxes still display zero conversations.

These changes repair reproducible recovery/diagnostic gaps. They are **not proof that the production outage has been resolved**.

## Files changed by this repair

- `support_email_provider.py`
- `support_email_workspace.py` (also has preserved prior send-status edits)
- `components/support_email/mail.js` (also has preserved prior send-status edits)
- `tests/test_support_email.py`
- `tests/test_email_connection_recovery.py`
- `tests/test_email_connection_status.cjs`
- `tests/fixtures/email_connection_preview.py`
- `docs/EMAIL_CONNECTION_RECOVERY.md`

## Validation

- Before the repair, new mocks reproduced absent reconnect behavior, indistinguishable errors and failure caching/display issues. These mock failures do not identify the production exception.
- **186 Email Python tests passed**, including 12 new recovery tests, Email V1/V2, performance/body caching, notifications, signatures, send status and reply defaults.
- **66 of 67 selected shell/navigation/search/Files Python regressions passed.** Pre-existing failure: `tests.test_top_bar.TopBarComponentTests.test_sidebar_is_compact_and_has_no_brand_or_section_headings` expects `resetInitialSidebarScroll`. Both the test and top-bar HTML exactly match HEAD and were not modified here.
- JavaScript checks passed: unavailable-vs-empty status, Email component (20 assertions), send status, composer/search focus (2,404 checks), app search, and notification badges (22 assertions).
- Changed Python compilation, component JS syntax and `git diff --check` passed. Only line-ending notices were emitted by Git.
- This is the relevant regression selection, not every test in the repository.

At 1920×1080, the bundled production Email component was exercised with a fabricated wire adapter. Timeout displayed the specific safe error and “Mailbox unavailable.” Restoring the fabricated server and refreshing loaded Inbox, Drafts, Sent, Archive, Junk, Trash, a custom folder, and the fixture conversation. The message opened with its lazy attachment metadata. No real mailbox or external storage was contacted. Screenshots: `output/EMAIL_CONNECTION_UNAVAILABLE.png` and `output/EMAIL_CONNECTION_RECOVERED.png`.

## Preserved behavior and readiness

This repair does not edit SMTP, signatures, MIME, recipient logic, global search, Files launcher, order notifications, account mapping or unrelated pages. Earlier local send-progress/reply-default edits remain intact; their tests pass. No email body/attachment persistence or settings changes were added. Files restoration tests pass.

No commit, push, deployment, Render mutation, credential read/change, live mailbox connection, email send or mailbox mutation was performed. The only production read was deployment history; log access did not succeed.

**Do not treat this as a confirmed immediate production fix.** The local recovery patch is tested, but the production cause remains unresolved pending the requested read-only log access and subsequent evidence. Nathan's approval is required before any deployment.
