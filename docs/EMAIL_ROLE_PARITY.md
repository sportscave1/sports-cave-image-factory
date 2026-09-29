# Email role parity — 29 September 2026

## Root cause and scope of evidence

`Workspace.send()` had an extra role-dependent gate for Reply, Reply All and
Forward. It loaded optional support-workflow metadata immediately before SMTP.
If that lookup failed, non-admin users received "Approval metadata is unavailable"
while admin continued. A needs-approval flag or conflicting metadata also blocked
only non-admin users. Existing regression tests explicitly required that divergence.

That reproducible code-level blocker is removed in accordance with the requested
policy: Email page permission authorizes the same mailbox operations for everyone.
No incident-specific staff session/log was available to prove which condition
occurred in the reported live failure. New Mail did not have this gate; if the
reported failure was specifically New Mail, its exact error still needs checking.

## Shared path and preserved permissions

The page and event handler still enforce `can_access_page(user, "Email")`.
The shared path is Workspace -> MIME assembly -> SendRegistry -> SMTPProvider ->
Sent reconciliation/IMAP APPEND -> mailbox refresh. No alternate staff transport
or credentials were introduced. SMTP and IMAP configuration already came from
the same environment, independent of user ID and role.

Inbox, body reads, live sync, refresh, search, Drafts, folder actions, attachments
and Sent already use the same provider and controller for every permitted user.
Mailbox settings are keyed by mailbox; only signature preference is queried by
user ID. Per-user session state isolates selection/compose state, not mailbox
ownership. Explicit Refresh performs the same authoritative provider read.

Optional support-review metadata still exists. It is no longer a send authorization
gate. Existing permissions for editing shared mailbox settings, signatures and
clearing an internal review flag remain unchanged. No administrator privileges
were granted to staff and no authentication code was changed.

## Signatures and Sent

Signature source, formatting, preference lookup and selection are unchanged.
The existing admin default is Nathan; the existing worker default is the `reina`
profile, displayed as Maria. A saved user preference continues to override defaults.
No signature was rewritten or copied between users.

After SMTP accepts, the existing shared path locates the real Sent copy by
Message-ID or saves the exact outgoing MIME according to mailbox policy. This
includes body/signature, recipient, subject, sender, Date and attachments. A new
session loads it from the provider, not an optimistic local Sent item.

Rejected/unknown transport outcomes cannot create false Sent copies. Accepted
delivery plus failed copy storage keeps the accepted receipt and offers existing
copy-only reconciliation. Uncertain APPEND is checked without blindly repeating
APPEND; Send is not automatically replayed. These mechanisms were not changed.
Existing safe errors/logging remain; no secrets are exposed by the new tests/UI.

## Files changed

- `support_email_workspace.py`: remove the optional metadata/role send gate only.
- `tests/test_support_email_v2.py`: update the two old divergent-policy contracts.
- `tests/test_email_role_parity.py`: 18 tests, including the existing 14-test Sent
  lifecycle contract rerun with staff and four role-paired tests.
- `docs/EMAIL_ROLE_PARITY.md`: this report.

## Verification

- Focused role-parity + existing V2 tests: 75 passed.
- Email discovery suite: 144 run, 143 passed, one SQL-dependent navigation test skipped.
- Support Email discovery suite: 212 passed.
- Python compilation of all three changed Python files passed.
- `git diff --check` passed; LF/CRLF messages were informational warnings.

Paired tests exercise New Mail, Reply, Reply All and Forward through identical
provider responses, existing user signature selection, attachments, metadata
outage, Send acceptance, real-provider-fixture Sent copies, fresh session reload,
Inbox receiving/refresh, Drafts and denied Email permissions. Existing review-flag
test now proves it does not gate staff send while its editing permission remains.
The staff Sent suite also covers rejection, uncertain send/append, failed copy
retry, interrupted runs, concurrency and duplicate-event protection.

Browser verification used the existing `tests/fixtures/email_send_preview.py`
with `?account=admin` and `?account=staff`. Both rendered the actual Email component,
used SMTPProvider against a fabricated connection, reached Sent, displayed their
correct signature and retained the sent message on mailbox Refresh. Staff also
returned to Inbox and refreshed incoming fixture messages. Real SMTP/IMAP are
blocked by this harness. These are role fixtures, not real authenticated logins;
fresh-session persistence is covered by provider-backed automated tests.

## Release/manual check

No migration or configuration change is required. No UI, signatures, credentials,
Campaigns, Automations or unrelated system code changed. No live mail sent, no
production data changed, no commit, push or deployment performed.

Safe to test locally. After separately approving/deploying, Nathan should log in
with each real Email-authorized account, send only to an approved internal mailbox,
check its own signature and Sent after refresh/relogin, and refresh Inbox. A live
staff New Mail failure would require its actual error/time for further diagnosis;
this patch does not claim to fix unrelated provider/network outages.
