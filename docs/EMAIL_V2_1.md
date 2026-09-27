# Email V2.1 — performance and workspace polish

## Profile recorded before changes

Baseline: `335c006` (deployed V2). The pre-existing `docs/EMAIL_V1.md` change and local
`tests/fixtures/email_desktop_preview.py` were present before this task and preserved.
No real mailbox/SMTP/Render access was used.

The actual path is component selection event → Email Streamlit fragment → `Workspace.open_thread`
→ sequential `related_headers(INBOX)` and `related_headers(Sent)` → thread rebuild →
`read_message(selected)` → `model()` → another fragment render → component `root.innerHTML`.
Each provider read creates/authenticates/selects/logs out its own IMAP connection. A custom-folder
click can add a third history connection, before the fourth connection reads the body.

Measured with the existing fabricated mailbox and explicitly simulated 180 ms history / 240 ms
body operations (not a measurement of VentraIP):

| Baseline path | Controller open | Model preparation | Provider calls |
|---|---:|---:|---|
| Cold Inbox message | 601.00 ms | 0.92 ms | Inbox history, Sent history, body |
| Immediate reopen | 0.07 ms | 0.35 ms | none |
| Reopen after 20-second cache expiry | 600.47 ms | 0.62 ms | Inbox history, Sent history, body |

The shared 40-entry/20-second cache mixes headers, folders, bodies and history; expiry of one
read prunes all expired entries. Every `model()` converts the displayed body/quote into safe HTML
again (four conversions across two no-op models) and rebuilds all list rows/signatures. Browser
render replaces the full workspace DOM, freezes all controls, and doesn't highlight the new row
until the server responds. Folder scroll is not preserved by that replacement.

**Already correct:** ordinary selection does not discover folders, load inbox headers/previews,
query orders/Supabase, or download attachment binaries. The page already uses a Streamlit fragment,
so unrelated OS pages do not rerun. Order matching is already on-demand in Customer / Order.

The Email page only removed bottom padding; it left Streamlit's content max-width and horizontal
gutters intact. Rows were 68 px, desktop folder width up to 194 px, and folders followed LIST order.

Raw local timing output: ignored `output/email_v21_before.json`. The reproducible baseline and
after outputs are `output/email_v21_baseline_reproduced.json` and `output/email_v21_after.json`.

## Completion report

1. **Root causes:** history searches and separate authenticated connections preceded the selected
   body fetch; the common 20-second cache expired bodies/history; every model reconverted HTML and
   rebuilt rows; the component replaced the whole workspace DOM and waited for the server to highlight.
   Folder/header/order/attachment work was already absent from ordinary selection.

2. **Unnecessary work removed:** no history search before the first body display, no repeated body
   reads after header TTL expiry, no repeated thread resolution within the same mailbox version,
   no repeated safe-HTML preparation for cached MIME, no unchanged row/signature reconstruction,
   and no folder/list/toolbar DOM replacement on message selection. The selected thread uses an index.

3. **Measured timings:** the repeatable profile uses simulated operation latency, not live VentraIP.

   | Path | Before open + model | After open + model | After provider calls before body display |
   |---|---:|---:|---|
   | Cold | 601.08 + 0.92 ms | 240.48 + 0.62 ms | selected body only |
   | Immediate reopen | 0.08 + 0.34 ms | 0.02 + 0.12 ms | none |
   | Reopen after header TTL | 600.65 + 0.62 ms | 0.01 + 0.07 ms | none |

   Deferred fixture history takes 360.97 ms after the first body display; it does not fetch bodies.
   Initial fixture loading is 2.13 ms (folder/header fixtures have no network delay). HTML conversions
   across two no-op models fell from four to zero. Order queries remain zero on selection.
   In the local browser with an intentionally **600 ms** body delay, highlight/loader was observed
   in **39 ms**, body in **763 ms**, and a cached body in **37 ms**. Browser observations include
   automation overhead and are individual observations, not production percentiles. No real-mailbox
   latency claim or guaranteed sub-second network response is made.

4. **Message/session caching:** session-owned LRU, at most 75 opened messages and 64 MiB of serialized
   content data, keyed by mailbox + folder + UIDVALIDITY + UID + Message-ID. It retains parsed body,
   prepared safe HTML/quote and attachment metadata. Python container overhead is additional.
   No body TTL; entries disappear on eviction/session loss/configuration or user-scope change.
   Refresh retains identity-matched immutable MIME and prunes invalid UIDVALIDITY entries.
   The browser has a separate transient 20-thread/8 MiB LRU of whitelisted safe display payloads
   for immediate paint; no localStorage, IndexedDB, disk persistence or credentials. It clears on
   mailbox version/error changes and agrees with the server's default active thread member.

5. **Thread cache:** session-owned LRU, 75 memberships/8 MiB, keyed by thread key + mailbox version.
   Existing Message-ID/References threading is retained. After the body paints, a 120 ms scheduled
   component event requests missing history headers only. Stale selection/version events are ignored.
   History failures leave the already loaded body visible with a restrained notice. No body prefetch
   or background listener was added. An in-flight history read can still delay a subsequent uncached
   fetch; the browser highlights immediately and queues the latest requested selection.

6. **Folder/header caches and Refresh:** discovered folders/counts/capabilities have a separate
   300-second display cache, checked only on mailbox loads. Headers/search keep the existing
   20-second cache and 50-message initial page. Selection does not call either loader, even after TTL.
   Refresh explicitly clears folder/header/history caches, rereads live data, increments mailbox
   version and invalidates browser views. It does not discard valid server body entries. Known
   writes invalidate header/history versions. Connection testing resets folder discovery. Leaving
   and re-entering Email still refreshes through the existing navigation epoch. TTL is not polling.

7. **Order matching:** already deferred to the Customer / Order drawer; retained. No order/database
   load occurs for list rows or message selection. The drawer uses the existing bounded synced-order
   loader and conservative matcher. Cached opened text supplies optional body order references.
   No Shopify calls or new order cache/database were introduced.

8. **IMAP:** a cold body open uses one authenticated, read-only connection for BODYSTRUCTURE and
   safe text-section BODY.PEEK reads. Historical selected-folder/Inbox/Sent reads now share one
   authenticated connection, with read-only selection per discovered folder, at most three folders
   and the existing bounded identifier/header limits. Connections always close; later operations
   reconnect cleanly. TLS, timeouts and safe errors remain unchanged; no persistent socket pool.
   Normal clicks retain Email fragment reruns. A full-render reconnect safely falls back to an app
   rerun when Streamlit rejects fragment scope; ordinary selection does not use that fallback.

9. **Attachments:** binaries remain explicitly requested only. Opening mail retrieves text sections
   and attachment filename/type/encoded-size metadata. Existing download/forward-attachment paths
   are unchanged. Preview loading remains bounded to small text snippets during header loads;
   selection never refetches previews or downloads complete MIME for a snippet.

10. **Mail truth/security:** VentraIP remains authoritative for Inbox, Sent and saved Drafts. No
    bodies, HTML, Sent copies, draft bodies or attachment binaries are written to Supabase. No
    database/schema/store changes. Display HTML uses the existing safe plain-text/HTML conversion,
    prepared once per body fetch; remote tracking content is not introduced. Logs contain operation
    class/timings only, never mail text or credential values. Timing instrumentation is local-only.

11. **Full width:** Email-only CSS removes the content max-width and large gutters. The OS sidebar,
    global styles and navigation are unchanged. The workspace has no outer card/border radius.

12. **Viewport height:** top padding uses `calc(var(--sc-topbar-height) + 6px)`. The component measures
    the remaining parent viewport below its actual frame top, subtracts 6 px, and updates height on
    resize. Grid/flex `min-height:0` and internal overflow contain scrolling. It posts height only
    when changed; no fixed desktop height. A 280 px minimum protects the existing small-screen view.

13. **Outer gaps:** verified 6 px left/right/bottom gaps. At 1920×1080 with a 300 px fixture sidebar,
    the mailbox is x=306, y=70, width=1608, height=1004. At 1440×900 it is width=1128, height=824.
    The fixture includes zero-height OS-style navigation bridges. Main/document heights match the
    viewport and outer scrollTop stays zero.

14. **Pane widths:** at 1920×1080: 188 / 390 / 1030 px (folders/list/reading). At 1440×900:
    170 / 330 / 628 px. Intermediate component widths use 180 / 360 / remaining space.
    Existing collapsed-folder and mobile modes remain. Rows are 60 px; toolbar/status line 43/23 px.

15. **Folder order:** Inbox first, then supported Flagged role if present, Drafts, Sent, Archive,
    Junk, Trash, then custom folders alphabetically. No synthetic Flagged folder or new feature
    is created. Current discovery supplies the six known standard roles. LIST names/mappings are
    unchanged; sorting is presentation only. Reversed fixture discovery still renders Inbox first.

16. **Scrolling/selection:** folder, conversation and reading panes scroll independently; toolbar
    stays fixed. Folder/list DOM stays mounted during selection and keeps scroll position. Reading
    selection resets its own scroll. Cached content paints immediately; missing content shows a
    reading-pane-only loader. Writes wait for the server to validate selection. Rapid clicks queue
    the latest selection without replacing the whole workspace. Refresh preserves an open composer.

17. **Search:** unchanged deliberate Search/Enter submission, including existing field prefixes and
    pagination. Typing does not call IMAP. Browser verification kept 50 rows while text was unsubmitted;
    submitting `subject: Delivery update` returned the fixture's 25 matching rows.

18. **Files:** runtime changes are `support_email_cache.py` (new), `support_email_workspace.py`,
    `support_email_provider.py`, `support_email_page.py`, `components/support_email/mail.js`, and
    `components/support_email/style.css`. Validation changes are `tests/email_v2_fixtures.py`,
    `tests/test_support_email_v2.py`, `tests/test_support_email_component.cjs`, new
    `tests/test_support_email_performance.py`, new `tests/profile_support_email.py`, and the previously
    untracked `tests/fixtures/email_desktop_preview.py`. This report is new. The pre-existing
    `docs/EMAIL_V1.md` change was left untouched. Ignored screenshots/logs/results are under `output/`.

19. **Targeted checks:** 124 Email Python tests pass (45 V1, 57 V2, 22 performance/cache).
    Node helper tests pass 20 assertions. Python compile checks pass for all nine changed/new
    Python files; JS syntax checks pass for component and test. `git diff --check` and Render topology
    validation pass. Tests cover cache reuse/invalidation/eviction, safe HTML, read-only BODY.PEEK,
    single-connection history, failure isolation, explicit search, no row-order reload, no persistence,
    and no Email calls from Home/Orders startup.

20. **Existing regression status:** ran ten suites separately: startup scope (6), navigation
    performance (23), sidebar cleanup (5), grouped routing (7), accounts (79), bounded orders (7),
    Orders UI (137), Home/dashboard (133), existing email service (6), Render topology (3).
    **404 pass; two pre-existing failures** in `tests.test_orders_loading_ui.EditionOpsUiTests`:
    `test_mockups_prompt_cards_use_compact_modal_prompt_actions` and
    `test_product_uploads_shows_only_selected_embedded_product_prompt`. Both fail against unchanged
    committed `HEAD:app.py` too; they assert old unrelated UI source strings. They were not modified.

21. **Browser validation:** passed with fabricated mailbox/SMTP/database/audit only, at 1920×1080
    and 1440×900. Verified available width/height, first Inbox, independent overflowing panes,
    60 px rows, fixed toolbar, immediate selection/loader/cached body, latest rapid-click selection,
    no list reset to top on selection, no page scroll, no horizontal overflow/overlap, intentional
    search, Reply All composer, compose text retained across Refresh, and settings/signatures.
    No browser JavaScript errors. Evidence: `output/email_v21_desktop.png` and
    `output/email_v21_1440.png`. This uses the real Email component with a fabricated OS shell,
    not a screenshot of production or a live-network benchmark.

22. **V2 preserved:** Compose, Reply, Reply All, Forward, Sent reconciliation, Draft saving/editing,
    Archive/Trash/Junk, read/unread/flag, attachments, search, signatures, approval gates, duplicate-send
    protection and SMTP architecture remain covered by the passing V2 suite. SMTP implementation,
    MIME construction, write protocols and workflow storage are unchanged. Only cache invalidation
    was added around existing writes; no real send/move/flag action was performed.

23. **Scope:** no unrelated Sports Cave module, sidebar, routing, Home, Orders, Fulfilment, Edition
    Ops, Meta, Resend, certificate or product logic changed. No commit, push, deployment, Render,
    DNS, mailbox configuration, credentials or production data action occurred. No new environment
    variables, migration, service or dependency is required. No CRM or new product feature added.

24. **Deployment assessment:** ready for Nathan's review and an approved deployment followed by
    a supervised live-read smoke test. Local evidence supports the optimization; real VentraIP
    network latency and production browser geometry remain to be confirmed. The two unrelated
    baseline failures mean the entire existing suite is not fully green. Do not deploy automatically.
    After approval, check opening/reopening a message, older thread expansion, Refresh, folder/search
    changes, independent scroll and compose preservation at Nathan's screen size. Stop here pending
    approval; no further email features or CRM work.

## Reproduce locally

```powershell
.venv/Scripts/python.exe -m tests.profile_support_email --baseline
.venv/Scripts/python.exe -m tests.profile_support_email
.venv/Scripts/python.exe -m unittest tests.test_support_email tests.test_support_email_v2 tests.test_support_email_performance -q
node --check components/support_email/mail.js
node tests/test_support_email_component.cjs
.venv/Scripts/python.exe -m streamlit run tests/fixtures/email_desktop_preview.py --server.port 8503 --server.headless true
```

The browser fixture blocks real IMAP/SMTP constructors and mocks all storage/audit operations.
It uses 75 fabricated messages, reversed discovery with 24 extra folders, a long scrollable message,
600 ms cold-body delay and 350 ms history delay. No real credentials are required. Open two messages,
reopen the first, type then submit a search, open Reply All and Refresh, and inspect each pane's scroll.
