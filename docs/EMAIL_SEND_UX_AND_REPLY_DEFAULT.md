# Email send UX and reply default — local implementation report

## Send experience

The composer now shows a compact gold stage-progress bar with a polite status region. The mailbox remains visible. Stages are 5% Validating message, 15% Preparing email, 45% Connecting securely, 60% Authenticating mail server, 75% Sending email, and 100% Sent. These are stage markers, not byte-transfer or time estimates. Signature and attachment preparation remain inside the existing MIME preparation step; no artificial intermediate timers were added.

Only the SMTP DATA acceptance response (250) triggers the green **✓ Sent** state. That update is displayed before connection cleanup and Sent-folder work finish. Separately, the composer shows **● Sent copy pending**, changing to green **✓ Sent copy available** only when the existing verifier finds the exact outgoing Message-ID in the discovered Sent folder. Successful APPEND alone is not treated as verified visibility.

The existing initial Sent check remains. While the completed composer is open, up to three automatic follow-up checks run at nominal intervals of 6, 12 and 24 seconds. Browser scheduling can delay them. Server-side guards enforce the operation ID, accepted state, maximum check count and at least five seconds between checks. Follow-ups only verify; they never send or append. **Check Sent copy** remains available as a manual fallback.

Accepted operations stay locked and show Close instead of Send. Sent content stays visible with editing, formatting, attachments and draft actions disabled. Existing operation-ID/fingerprint duplicate protection remains; the registry now records acceptance before connection cleanup so an interruption cannot downgrade a known accepted receipt. Operation ID, Message-ID, send status and Sent-copy status survive ordinary session reruns. No new body or attachment persistence was introduced.

Known rejection shows **✕ Not sent / Could not send this email** and **Try again**. Try again prepares a fresh operation; it does not automatically send. An uncertain result shows **⚠ Send status uncertain / Do not resend yet**, keeps Send disabled and never automatically retries.

## Reply default

New Reply and Reply All drafts initialize `include_quote=False`. Forward retains `True`. The checkbox remains available. Only new-draft initialization changed: existing draft restoration and user edits retain the saved choice, and reruns do not force the checkbox off. A separate new reply starts unchecked again.

Message-ID, In-Reply-To, References, recipient logic, Nathan/Maria signatures, account mapping, MIME construction, attachments and draft storage are unchanged.

## Files changed

- `components/support_email/mail.js`: status rendering, live stage updates, action locking and bounded Sent polling.
- `components/support_email/style.css`: compact progress/status styling.
- `support_email_progress.py`: transient stage-only Streamlit-to-component bridge.
- `support_email_page.py`: connects the bridge only for Send events.
- `support_email_smtp.py`: optional display callbacks and early accepted-receipt bookkeeping; transport configuration and commands unchanged.
- `support_email_workspace.py`: session progress/copy state and guarded automatic verification.
- `support_email_compose.py`: new reply quote default.
- `tests/test_email_send_ux.py`: send safety, progress, verification and reply/draft regression tests.
- `tests/test_email_send_status.cjs`: status semantics and bounded polling tests.
- `tests/test_support_email_signatures.py`: explicitly enables quotes in tests whose purpose is signature placement above quoted history.
- `tests/fixtures/email_send_preview.py`: fabricated SMTP/IMAP browser fixture with real network constructors blocked.
- `docs/EMAIL_SEND_UX_AND_REPLY_DEFAULT.md`: this report.

## Validation

All selected checks passed:

- 174 Python tests across send UX, Email V1/V2, signatures, performance and notifications.
- 34 Python navigation/startup/sidebar regressions.
- JavaScript send-status and bounded-polling checks.
- Existing Email component checks: 20 passed.
- Composer/global-search focus checks: 2,404 passed.
- JavaScript syntax check, Python compilation of all changed/new Python files, and `git diff --check`.

This was the relevant regression selection, not the entire repository test suite. No failures occurred in that selection.

The installed Streamlit version supports the progress bridge but logs a deprecation warning for `components.v1.html`. The bridge was verified in that runtime; its API should be migrated when upgrading Streamlit to a version that removes it.

Browser verification used the real Email component in a local fabricated mailbox harness at a 1440×900 desktop viewport. Verified live connecting/authenticating/sending progress; delayed Sent copy transitioning from pending to available; immediate Sent copy; rejected send with Try again; uncertain outcome with Send disabled; accepted content remaining visible and locked. New Reply was unchecked; manual opt-in survived saving/rerendering. Automated round-trip tests cover checked and unchecked saved drafts, Reply All, Forward, threading, and both Nathan and Maria. A complete production shell/live mailbox test was not performed.

Screenshots are in `output/EMAIL_SEND_PROGRESS.png`, `output/EMAIL_SENT_COPY_PENDING.png`, `output/EMAIL_SENT_COPY_AVAILABLE.png`, `output/EMAIL_SEND_UNCERTAIN.png`, and `output/EMAIL_QUOTE_CHOICE_SAVED.png`.

## Boundaries and readiness

VentraIP remains authoritative. No email body or attachment was added to Supabase storage. SMTP authentication/configuration, IMAP architecture, MIME, signatures, caching, search and unrelated OS modules were not changed. The only transport-adjacent changes are the optional progress hooks and accepted-receipt bookkeeping described above.

Ready for an approved deployment and controlled smoke test based on local fixture/regression results; live production behavior has not been tested. No commit, push, deployment, real email, Render change or VentraIP change was performed. Work stops here pending Nathan's approval.
