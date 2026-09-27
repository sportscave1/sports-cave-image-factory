# Email notifications — local implementation report

27 September 2026. Implemented locally against fabricated mailbox/database data.
No commit, push, deployment, real mailbox action, SMTP send, Render, DNS, VentraIP
or Resend change was performed.

## Existing architecture and integration

1. **Orders architecture found:** `top_bar.py` supplies a signed, permission-scoped
   configuration to the existing parent-document top bar. Its Orders status API
   loads an action-required summary with a 30-second server display cache. The
   browser polls every 60 seconds and retains its display state in sessionStorage.
   Order popup events originate in `webhook_events`; per-user consumption cursors
   live in `app_sync_state`. The bell independently reads approved `audit_logs`
   activity events through `/api/os/top-bar/notifications`.
2. **Reused components:** the existing top bar, bell button, notification panel,
   notification row renderer, route navigation and sidebar badge renderer/styles.
   The Orders badge helper now delegates to a shared helper; the class remains
   `.sc-orders-action-badge`. No second notification panel or table was created.
3. **Email badge source:** real INBOX `UNSEEN`, never the number of OS notifications
   or loaded conversation rows. Zero hides the badge. Counts above 99 follow the
   existing `99+` convention; the accessible label retains the actual count.
4. **IMAP command:** `STATUS "INBOX" (UNSEEN MESSAGES UIDNEXT UIDVALIDITY)` over the
   existing verified TLS connection/authentication helper. The standalone
   `get_unread_count()` method performs this lightweight status operation without
   SELECT or FETCH. No folder discovery or conversation build is needed globally.
5. **Refresh:** Email runs concurrently with Orders on its existing 60-second
   schedule, including users who have Email access without Orders access. A
   30-second process cache and durable check timestamp coalesce users/reruns.
   Global Refresh clears the browser Email status cache and requests status again,
   respecting the server TTL. Explicit Email refresh/read/unread/move actions
   invalidate the server count cache. Their freshly read folder count updates the
   sidebar immediately. Global status updates also patch the Email folder count
   without re-rendering conversations or fetching bodies.
6. **Visual match:** Orders and Email use the identical badge class and creation
   helper: 25px minimum width, 20px height, 11px font, same muted background and
   right alignment. Browser measurements confirmed equality at both requested
   desktop resolutions. There is no special Email badge colour or component.
7. **New arrivals:** UIDNEXT is compared with the persisted cursor. An unchanged
   mailbox requires only STATUS. New UID ranges use read-only SELECT and one
   bounded UID FETCH requesting only From, Subject, Date and Message-ID. The
   command uses `BODY.PEEK[HEADER.FIELDS (...)]`: this is header-only IMAP syntax,
   not message body content. At most 50 UID positions are handled per check.
8. **Durable deduplication:** one shared mailbox cursor in existing `app_sync_state`.
   New events are minimal `new_email_received` entries in existing `audit_logs`.
   Identity hashes mailbox + INBOX + UIDVALIDITY + UID. A non-blocking PostgreSQL
   advisory transaction lock serializes the mailbox check. Event insertion and
   cursor advancement commit together; retries and rolled-back transactions do
   not duplicate or lose committed notifications. An identity check also protects
   against an older restored cursor. No new schema, table or migration.
9. **First deployment:** a missing cursor records current UIDNEXT minus one and
   UIDVALIDITY without generating historical notifications. Existing unread mail
   still contributes to the badge. UIDVALIDITY changes establish a fresh baseline
   rather than announcing the rebuilt Inbox as new mail.
10. **Restart:** the cursor survives application restarts in existing durable
    storage. Session state is only a display optimization. If persistence is
    unavailable, the count may still be shown via STATUS, but no undeduplicated
    arrival alerts are created. Polling resumes when storage recovers.
11. **Bell appearance:** the existing notification row shows an envelope, “New
    email”, sender and subject. Metadata is escaped and length-bounded. No body,
    attachment content, raw credentials or raw header dump is displayed. Existing
    order events retain their renderer and selection rules. The current bell has
    no unread number or relative-time display; this task preserves those existing
    conventions rather than adding a separate Email counter/read model.
12. **Click-through:** the existing navigation routine receives an Email deep link
    carrying `email_uid`, `email_uidvalidity` and `email_message_id`. It works when
    Email is already open as well as from another page. The existing dropdown
    closes normally. No new OS-notification read/dismiss persistence was invented:
    current bell items navigate but are not durably marked read on click.
13. **Message selection:** the authorized Email page opens INBOX, resolves the
    exact UID/UIDVALIDITY and verifies Message-ID where available. An exact
    Message-ID header search is the conservative fallback. Messages outside the
    latest 50 can be selected with one targeted header fetch. Missing/ambiguous
    targets leave the Inbox usable with a restrained notice. Body loading occurs
    only here, through the existing on-demand body cache. No Seen flag is changed.
14. **Read-state separation:** bell activity history and mailbox Seen flags remain
    distinct. Opening an email does not reduce unread count. The existing explicit
    Mark read/Mark unread actions change real mailbox flags; fresh STATUS counts
    then update both sidebar and Email folder display.
15. **Shared mailbox:** the cursor, events and mailbox unread count are shared.
    Nathan and Reina/Maria with Email permission see the same mailbox state after
    refresh. Email events are visible to Email-authorized users regardless of the
    narrower actor filter used for ordinary staff activity-log notifications.
    Existing non-email activity permission rules remain unchanged.

## Performance, persistence and verification

16. **Fixture measurement:** 50 unchanged checks averaged **13.537ms** including
    Python SSL-context construction and mocked database/IMAP work. A cached check
    averaged **0.0022ms**. Normal application-issued commands were LOGIN, STATUS,
    LOGOUT: one authenticated connection, one tiny status response, no SELECT or
    FETCH. Cached checks made zero IMAP calls. Real server greeting/capability,
    DNS, TLS handshake, network and PostgreSQL latency were not measured.
17. **No global body loading:** zero message-body/attachment fetches in the timing
    probe. No inbox list load, previews, Sent search, order loader, thread building
    or message parsing beyond the selected minimal headers occurs globally.
18. **No content duplication:** only unread/cursor timestamps and allowed event
    fields (mailbox/folder/UID identity, sender, subject, Message-ID, received time)
    are persisted. No email body, HTML body, attachment bytes or draft/Sent copy is
    stored in Supabase. VentraIP remains authoritative. Failures log only safe
    exception class names, are throttled, and never fabricate zero unread. A last
    known badge can survive up to 120 seconds, then is hidden as unavailable.

19. **Files changed for this task:**

    - `support_email_notifications.py` — new lightweight cache/cursor/audit service.
    - `support_email_provider.py` — STATUS, bounded new-header check and targeted link lookup.
    - `support_email_page.py` — consume notification query parameters once.
    - `support_email_workspace.py` — shared count invalidation/publication and exact selection.
    - `top_bar.py` — Email endpoint and permission configuration.
    - `top_bar_api.py` — permission-scoped Email status and existing bell event mapping.
    - `components/sports_cave_top_bar/index.html` — shared badge, polling and deep-link integration.
    - `components/support_email/mail.js` — patch Inbox count from the shared top-bar status.
    - `tests/test_support_email_notifications.py` — provider, persistence, cache, API and workspace tests.
    - `tests/test_email_notification_component.cjs` — execute shared badge helper assertions.
    - `tests/profile_email_notifications.py` — reproducible fixture timing probe.
    - `tests/fixtures/email_notification_runtime.py` — shared fabricated mailbox/database.
    - `tests/fixtures/email_notifications_preview.py` — actual top bar/component in a local mock shell.
    - `docs/EMAIL_NOTIFICATIONS.md` — this report.

    The pre-existing `docs/EMAIL_V1.md` edit was preserved. The signature work was
    already present and was committed separately during this task; this task did
    not commit it or alter signature behavior.

20. **Targeted results:** all **22 new notification tests** and all **146 existing
    Email tests** passed (V1 45, V2 57, performance 22, signatures 22). JavaScript
    checks passed: shared badge helper 22 assertions; existing Email component 20.
    Python compilation covered all ten changed/new Python files. Both changed
    JavaScript sources passed syntax checks, including the extracted top-bar script.
    `git diff --check` passed.
21. **Regression results:** navigation performance 23, startup scope 6, sidebar
    navigation 5, account system 79 and email service 6 passed. Existing top-bar
    and Orders notification suites ran 60 tests with **three pre-existing failures**:

    - Sidebar source assertion expects removed `resetInitialSidebarScroll` text.
    - Order status test expects 1 but receives a prior test's cached count of 15.
    - Order UI source assertion expects a literal 30-second timer; HEAD already uses
      the 60-second named constant.

    All three reproduced against the unchanged HEAD top-bar component. The Orders
    loader, cache and endpoint function ASTs also match HEAD exactly. The aggregate
    single-process test run exposed 22 account-test failures from shared Streamlit
    test context; the independent account suite passed all 79 tests. Counting the
    independent successful account run: **344 passed, 3 pre-existing failures**
    across the 347 selected Python tests. This is not a claim that every repository
    test was run or that the existing suite is entirely green.
22. **Browser verification:** actual production top bar and Email component with
    fabricated providers, at **1440×900** and **1920×1080**. Orders [7] and Email [3]
    matched size and alignment; order and email appeared together in the existing
    bell; click-through opened UID 4 / UIDVALIDITY 500 and its message; opening kept
    unread at 3. Mark read/unread changed sidebar and folder count immediately;
    reducing all fixture unread messages to zero removed the badge, and restoring
    unread restored it. No whole-workspace reload was introduced for count updates.
    Screenshots: `output/EMAIL_NOTIFICATIONS_1440.png` and
    `output/EMAIL_NOTIFICATIONS_1920.png`. One transient MutationObserver console
    error appeared during development reload/reconnection; functional checks passed.
23. **Orders preserved:** no change to order count calculation, popup consumption,
    webhook behavior, summary cache, event priority or existing route behavior.
24. **Scope preserved:** no unrelated business module, SMTP, compose, reply, draft,
    signature or mailbox content-cache behavior was changed. No CRM or browser/OS
    push notifications were added. UI fixture providers prevent real mailbox I/O.
25. **Deployment readiness:** ready for Nathan's review and an approved deployment
    with a controlled live acceptance test. No new environment variables or
    migrations are required. Real VentraIP latency and durable PostgreSQL execution
    remain untested here; all I/O verification was mocked. The mailbox is polled
    while an authorized OS browser is active, not by a new background service.
    Large arrival backlogs/UID gaps drain in bounded 50-UID windows on subsequent
    polls. Do not call production behavior verified until the live acceptance test.

## Repeating the local checks

Run `python -m unittest tests.test_support_email_notifications -q`,
`node tests/test_email_notification_component.cjs`, and
`python -m tests.profile_email_notifications` using the repository runtime.

For UI inspection, run
`.venv/Scripts/python.exe tests/fixtures/email_notifications_preview.py --serve`,
then open `http://127.0.0.1:8504/`. It establishes a historical baseline and adds
one fabricated arrival. Use the normal bell and Email actions; all data is mock.
Stop this server after testing. Never add real credentials to this fixture.

After an approved deployment: confirm initial unread count without a historical
bell flood; arrange one controlled incoming message; check one bell event after
the existing poll; restart and confirm no duplicate; open via bell without marking
read; explicitly toggle read/unread and confirm both users' counts after refresh.
