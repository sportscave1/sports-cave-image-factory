# Email V2.2 connection recovery — local repair, 27 September 2026

No commit, push, deployment, configuration change, real mailbox connection or real
mailbox mutation was performed. Read-only Render deployment history and logs were
inspected for the existing canonical `sports-cave-os` service.

1. **Root cause confidence.** Production failure is confirmed at IMAP connection
   construction, before LOGIN, SELECT or LIST. The old log records only `OSError`,
   so the underlying network/server cause cannot be identified conclusively.
   Connection-limit rejection is a hypothesis, not a confirmed diagnosis.
   Confirmed code weaknesses are independent per-session polling, immediate
   background retries, forced full reloads on unsuccessful cold starts, repeated
   rerun attempts after a five-second guard, and clearing successful views on a
   failed foreground refresh. These are repaired locally.

2. **Evidence.** Render shows V2.2 live at 08:06:52 UTC / 18:06:52 Sydney.
   Sixteen matching warnings from 08:07:31 through 08:11:33 UTC all say
   `stage=connect code=temporary type=OSError`, approximately four failures/minute,
   including pairs eight seconds apart. The same filtered query from the prior
   deployment's live time through replacement returned no matching Email warnings.
   There are no logged authentication, LIST or connection-limit details proving
   those causes. Healthy connection counts were not previously logged.

3. **Last working boundary.** `03510291f4589c841f8fc3ac6507a89f8b04f9ba`
   (`Improve email send UX and mailbox recovery`) is the immediately preceding
   production deployment, matching Nathan's reported working version. Its live
   time was 06:42:52 UTC. This is a deployment/user-evidence boundary, not a live
   mailbox test performed by Codex.

4. **First affected deployment.** `332acc9b0040f10c42ef33cb36131fea96996204`
   (`Deploy Email V2.2 live mailbox updates`). Its 21-file change added the shell
   Email heartbeat, `ImapProvider.live_changes`, Workspace live/read/action logic,
   context menus, fixtures and tests. It did not change configuration names,
   credentials, `_connection`, SMTP, Files or search implementation. Working tree
   and HEAD were stable during this repair; no concurrent commits were observed.

5. **Poll sources before repair.** One existing global notification/status check
   feeds both badge and bell. V2.2 added one independent live check per Email
   session. This is `2 + 2N` connections/minute for N active views, before user
   actions/retries: about 10/minute for Nathan and Maria with two tabs each.
   Folder discovery (LIST plus up to six optional STATUS counts), header loads,
   uncached bodies, flag changes, move/copy actions, downloads, draft operations,
   historical thread resolution, Sent verification and Refresh are separate
   bounded foreground sources. SMTP itself is separate. Orders, search and Files
   do not create extra IMAP pollers. Production is one service instance with one
   Uvicorn process; additional processes would multiply process-local bounds.

6. **Leaks/multiplication.** No accumulating worker threads, shared raw sockets or
   confirmed socket leak was found. The component has one fallback timer, but a
   shell-mount race could leave fallback and shell heartbeat both active. The
   fallback now relinquishes ownership when the shell appears; pagehide cleans
   it up. No timer is created on component render. Connection cleanup is hardened
   for partial construction, logout failure and interruption.

7. **Architecture after repair.** `support_email_runtime.py` coordinates short
   status/flag/header snapshots per mailbox configuration within the process.
   Equivalent live checks coalesce across sessions; callers get independent data
   copies. Raw IMAP sockets are never cached/shared. At most two connections may
   be active, at most one background connection, with capacity reserved for
   foreground actions. Background work never waits behind a network operation;
   foreground admission waits no longer than the configured timeout. Background
   attempts have an additional six-per-rolling-minute ceiling per mailbox.

8. **Interval.** Normal IMAP checks and transient snapshot TTL are 60 seconds.
   The existing OS heartbeat remains 30 seconds so Orders semantics stay intact;
   Email's 55-second scheduling guard coalesces those ticks into roughly one
   check/minute. Hidden/busy Email components skip checks. No IDLE worker or new
   permanent server timer was introduced.

9. **Backoff.** Failed connections impose shared 15, 30, 60, then 120-second
   maximum cooldowns. Workspace and notification checks respect bounded retry
   timestamps, so ordinary reruns cannot reconnect repeatedly. Actual attempts
   occur on the next eligible heartbeat. Success resets backoff. Capacity skips
   are distinguished from outages and do not falsely change Live to offline.

10. **Cleanup.** Each bounded operation logs out in `finally`, attempts transport
    shutdown, and closes any remaining file/socket resources. Partially created
    SSL objects also release resources. No IMAP CLOSE or EXPUNGE is used. Safe
    constructor/command failures, cancellation and failed logout are tested.

11. **Shared status and durable notifications.** A cached
    `STATUS INBOX (UNSEEN MESSAGES UIDNEXT UIDVALIDITY)` snapshot feeds the global
    badge/bell detector and live Inbox checks. A separate loaded-UID FLAGS check
    remains necessary for changes made in Thunderbird when aggregate counts do
    not change. New arrivals fetch only bounded headers. The unchanged durable
    UIDVALIDITY/UID cursor and existing event transaction prevent historical
    floods/restart duplicates. No database tables, SQL or data were changed.

12. **Outage UI.** The successful folder/list/selected-message snapshot and unsent
    composer remain visible for the session with an amber interruption notice,
    last-success time and `Cached mailbox · last successful view`. Cold failures
    still show Mailbox unavailable. A failed request for a different folder or
    search never labels the old Inbox as that new view. Failures do not populate
    successful data caches; successful recovery clears interruption state.

13. **Retry/Refresh.** Safe foreground read methods retain at most one fresh
    retry. Live background reads no longer retry immediately. Writes are never
    replayed. Manual Refresh bypasses cooldown for its controlled operation and
    invalidates transient generations, so an older concurrent poll cannot
    repopulate shared state. It does not create another timer. Successful flag
    actions invalidate shared snapshots; existing immediate local badge updates
    and automatic mark-read behavior remain.

14. **Diagnostics.** Safe categories now distinguish DNS, TLS, timeout, refused,
    network unreachable, reset/EOF, server BYE, explicit connection/rate limit,
    authentication, LIST, STATUS and protocol errors. Connection warnings include
    stage, category, exception type, numeric errno/winerror and elapsed time.
    Successful check/start timing is debug-level. No raw exception response,
    password, auth payload, body or attachment is logged. The existing IMAP env
    names, including `SPORTSCAVE_EMAIL_PASSWORD`, remain valid. Notification
    checks use the existing eight-second provider timeout instead of a separate
    three-second override.

15. **Files changed.** Production: `support_email_runtime.py` (new),
    `support_email_provider.py`, `support_email_notifications.py`,
    `support_email_workspace.py`, `components/support_email/mail.js`.
    Tests/fixtures: `tests/test_email_poll_recovery.py` (new),
    `tests/test_email_connection_recovery.py`, `tests/test_email_live_component.cjs`,
    `tests/test_support_email_live.py`, `tests/test_support_email_notifications.py`,
    `tests/test_support_email_v2.py`, `tests/fixtures/email_notification_runtime.py`,
    `tests/fixtures/email_notifications_preview.py`. Documentation: this file.

16. **Validation.** Final targeted Email/provider/live/recovery/performance/
    notification/signature/send suite: **225 passed**; the existing email-service
    suite also passed all **six** tests. Seven JS suites passed:
    live/menu/timer (73 assertions), connection state, shared badge (22), send
    state, component/cache (20), composer/search focus (2,404), app search.
    All 11 changed Python files compile; JS syntax and `git diff --check` pass.
    Broad-suite checkpoint: 3,262 tests, 131 failures, 36 errors, 36 skipped.
    A clean HEAD export ran 3,249 tests with the same 131 failures and 38 errors;
    **no new failing test identities**. Its two extra errors concerned mockup
    output generation and a Files test requiring Git export context. Final
    targeted checks were rerun after subsequent cleanup/backoff edge tests.
    Adjacent top-bar/order/startup/Files suite: 75 tests, three pre-existing
    failures (sidebar source assertion and two Orders notification assertions).

17. **Connection-load simulation.** Fabricated wire transports; virtual time;
    no VentraIP network latency:

    | Scenario | Duration | Sessions | Calls including reruns | Connections | Peak | Closed | Leaked | STATUS | Body fetches |
    | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
    | Healthy | 10 min | 4 | 400 | 20 | 1 | 20 | 0 | 10 | 0 |
    | Two-minute outage and recovery | 10 min | 4 | 400 | 19 | 1 | 19 | 0 | 8 | 0 |

    Latest execution took approximately 305 ms and 281 ms respectively for the
    entire simulations. These are fixture execution times, not production
    network latency. A separate concurrent test reached two admitted operations,
    deferred another background check, and returned to zero active operations.
    Distinct-view tests enforce the six-background-attempt/minute ceiling.

18. **Browser verification.** Used the real production Email component/top bar
    with the fabricated OS-shell fixture at 1440x900 and 1920x1080. Verified healthy
    Live state; one-shot timeout without clearing an opened message; automatic
    return to Live; a sustained two-minute outage; new mail appearing after
    automatic recovery with badge/count increase; and manual Refresh during
    failure then recovery. Unsent reply text, selection and Nathan signature
    survived. A separate staff session showed Reina internally and Maria in
    Compose. No real send was attempted. Captures are in
    `output/email-recovery-outage.png` and `output/email-recovery-live.png`.

19. **SMTP unchanged.** SMTP configuration/authentication, MIME generation,
    recipients, duplicate-send protection, sending progress and Sent Message-ID
    policy were not edited. IMAP admission/cleanup also protects the existing
    bounded Sent verification calls; it does not resend messages.

20. **Signatures and other modules unchanged.** Nathan/Maria mapping, signatures,
    attachments, body cache implementation, search, Files, Orders and all other
    OS modules are unchanged. No Supabase body/attachment persistence was added.
    VentraIP remains authoritative; only transient display metadata is shared.

21. **Live updates preserved.** Automatic arrivals, real read/unread, immediate
    local counts, durable bell events, row/folder menus, move/copy and folder-read
    behavior are retained. Background checks never fetch message bodies or
    attachments, search Sent, load orders or initialize unrelated pages.

22. **Deployment assessment.** Ready for Nathan's review as a tested reliability
    repair and diagnostic improvement. It cannot be certified as the definitive
    production outage cure because existing logs omit the underlying OSError
    cause and no real mailbox test was authorized. After an approved deployment,
    verify fresh folder loading and repeated live cycles, and inspect new safe
    errno/category logs if connection construction still fails. Do not change
    credentials based on the current evidence. No deployment has been performed.
