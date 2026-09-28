# Support Email send and Sent storage

This change only affects the human support mailbox. The existing VentraIP SMTP
and IMAP configuration and credentials remain in use. CRM/Resend is unrelated.

## Diagnosis from the existing code

`SMTPProvider.submit` submits exact MIME through authenticated TLS SMTP and treats
the final SMTP DATA 250 response as acceptance. The old component immediately
displayed a hardcoded 5%. Further progress depended on a second Streamlit srcdoc
iframe posting into the mailbox iframe. These display calls were inside the
send operation; interrupted Streamlit runs could skip its remaining work. The
component rendered the old model before handling the event and needed another
rerun to receive the result. There was no recovery from the process-wide accepted
receipt into a finished workspace operation.

Successful submission kept the composer open. It invalidated a cache but neither
selected nor reloaded Sent. The default `sent_policy=verify` only searched IMAP;
it never appended a missing copy. Even an acknowledged APPEND was displayed as
pending until a separate verification succeeded.

No live delivery or live SMTP auto-filing behavior was tested. The implementation
supports both existing provider copies and the explicit confirmed-server-saving
setting without replacing the transport.

## Current lifecycle

1. Explicit Send validates permissions, approval requirements and draft/MIME.
   Invalid content stays editable and sends nothing.
2. The frozen operation and MIME enter SENDING. The component displays a stage,
   not a percentage, and continues that confirmed operation.
3. The process-wide registry claims `(mailbox, operation UUID)` before SMTP. A
   repeated event, Ctrl+Enter, concurrent request or rerun cannot submit it again.
4. DATA acceptance records the Message-ID and UTC sent timestamp before cleanup.
   The operation enters SAVING_SENT_COPY. Storage and refresh finish server-side
   without another browser request or Streamlit display callback inside I/O.
5. SENT closes the completed composer, clears progress, selects Sent, removes the
   old search filter, loads fresh real IMAP headers and opens the matching message.
   The success receipt remains visible above the mailbox.

The state retains the SMTP result separately from the storage result. Reading a
workspace model never performs transport or copy writes. If an interrupted run
has an accepted registry receipt, it can resume only the remaining storage work.
An uncertain SMTP outcome blocks resubmission; it is never described as a known
failure. Known rejection allows an explicit reviewed retry with a new operation.

## Sent folder and duplicate protection

Folder mapping uses observed IMAP LIST names: configured override or unique
SPECIAL-USE role, then one unambiguous exact fallback (`Sent`, `Sent Items`,
`Sent Messages`, `INBOX.Sent`). Ambiguity requires mapping in Email settings.
No folders are created.

Automatic (the existing `verify` settings value) searches the exact Message-ID and
appends missing MIME. `server` continues to wait for confirmed server-side filing;
its bounded follow-up checks are read-only. `append` also searches before writing.

APPEND uses the original MIME bytes with `\Seen`. From/To/Cc, Date, Message-ID,
plain/HTML alternatives and attachments are unchanged. Bcc remains in the SMTP
envelope and is not disclosed in transmitted headers. Sent remains a real IMAP
folder including messages from other email clients, using normal threading,
newest-first sorting, body reading and attachment download paths.

Per-operation copy locks and receipts prevent concurrent/repeated APPENDs. A
successful APPEND remains successful even before a subsequent search can see it.
If APPEND was definitely not started or explicitly rejected, the UI offers
**Retry saving Sent copy**. It searches again first and never calls SMTP. If
APPEND acceptance is uncertain, only **Check Sent copy** is offered; the app will
not blindly append another copy. Rendering and automatic polling never retry a
write. APPEND invalidates shared mailbox snapshots.

## Failure and retention limits

After SMTP acceptance, copy/refresh errors keep SENT and show a storage warning.
Pending copies retain their frozen MIME across new compose sessions in the same
Streamlit session. At most five unresolved copies are retained (maximum existing
20 MB MIME limit each); resolve those before sending more. This is not a durable
outbox: a server restart or expired browser session can discard pending copy
bytes. Saved messages persist in IMAP. No new database schema or credential store
has been added, and no email is automatically replayed after restart.

## Local verification

- Python: `python -m unittest discover -s tests -p 'test_*email*.py' -q`
- Node: run all `tests/test_*email*.cjs` scripts.
- UI: run `streamlit run tests/fixtures/email_send_preview.py --server.address
  127.0.0.1 --server.port 8506 --server.headless true --browser.gatherUsageStats false`,
  then `node tests/verify_email_sent.cjs` with Playwright on NODE_PATH if needed.
- The browser fixture blocks real SMTP/IMAP, mocks persistence and uses fabricated
  `.test` addresses. Tests verify 1440×900 and 1920×1080 success, copy-only retry,
  rejected/uncertain delivery, and immediate/delayed server copies. Screenshots
  and results are written under `artifacts/email-sent-verification/`.

No live emails, commits, pushes or deployments are part of this work. One controlled
manual email test in the updated app is the remaining live integration check.

## Changed-file manifest

Application: `support_email_workspace.py`, `support_email_smtp.py`,
`support_email_provider.py`, `support_email_page.py`,
`components/support_email/mail.js`, `components/support_email/style.css`.
Removed obsolete iframe bridge: `support_email_progress.py`.

Tests and fixtures: `tests/test_email_sent_lifecycle.py` (new),
`tests/verify_email_sent.cjs` (new), `tests/test_email_send_status.cjs`,
`tests/test_email_send_ux.py`, `tests/test_support_email_v2.py`,
`tests/test_support_email_component.cjs`, `tests/email_v2_fixtures.py`,
`tests/fixtures/email_send_preview.py`.

Documentation: `docs/EMAIL_SENT_LIFECYCLE.md` (new). Browser screenshots/results and
the Python test log are local verification artifacts, not application resources.
Pre-existing CRM and other worktree changes were preserved.
