# Email, Campaigns and Automations performance audit

Local verification: 28 September 2026. No production deployment or service access.

## Findings and changes

The largest avoidable cost was Campaign preview switching. A device click ran the
whole page, then explicitly requested another full rerun. In the local profile
that meant 15 database reads and 29 sanitizer calls for one switch. The preview
is now a Streamlit fragment: its callback updates the selected device first,
then only the preview panel reruns. The existing iframe receives the same safe
HTML at a different width. The rest of the workspace remains mounted.

The shared Flow preview uses a separate presentation-only fragment. Flow source
editing still runs the parent page, preserving its existing dirty/review/save
checks. Width and display changes cannot fetch the flow list, load template
snapshots, calculate audiences, or call Shopify.

`crm_preview_cache.py` stores pure rendered output in the current Streamlit
session. A deterministic SHA-256 key includes rendering content, section HTML,
subject/preheader, market, renderer version, campaign key, rendering settings and
images-off mode. Unrelated notes/review/audience metadata do not cause rendering.
The document is validated even on cache hits. Entries are defensive copies,
bounded to four entries and 1 MiB of output; errors are never cached. No delivery
decision, permission, audience, provider credential or database result is cached.
Test sending continues to use the existing fresh canonical renderer and preflight.

Campaign initial load queried the same Header/Footer lists twice: once for
defaults and again for selectors. One request-local result now serves both,
reducing initial reads from 12 to 8. A full authoring rerun still reads current
settings/templates from storage. This is not a database TTL cache. Sectioned HTML
also imported/sanitized the body before importing it again with its sections;
the first discarded import was removed without changing the output.

Flows fetched and converted the selected template on every rerun, even when
`setdefault` discarded the result in favor of the open draft. Initialization now
occurs only when that selected email has no session snapshot. Selecting another
email or explicitly reloading still loads its saved source. Full page runs still
read current flow status; saving still checks versions under the existing lock.
One database read and unnecessary snapshot conversion are avoided on full reruns.

## Inbox trace

The existing mailbox already has careful lazy loading, so it was retained:

- Initial/return navigation loads configuration, discovers folders if needed,
  fetches one header page, then selects and loads only the chosen conversation.
- Folder metadata has a 300-second cache; list display data has a 20-second cache.
  Header loading uses UID/flags/date/header fields and bounded text snippets,
  not all MIME bodies or attachments. Short snippets can still require IMAP
  BODYSTRUCTURE/PEEK reads; remote mailbox latency remains relevant.
- The selected body cache includes mailbox, folder, UIDVALIDITY, UID and Message-ID.
  It is bounded to 75 entries / 64 MiB. MIME parsing, safe body and quoted text are
  reused. Attachments download only on request.
- Conversation-history expansion is deferred by the existing component, with
  selection/version guards. Related-folder headers share one read connection.
- Customer/order enrichment happens only when its drawer is requested, after the
  initial message. It does not block the initial reading-pane paint.
- Explicit refresh and mailbox mutations invalidate headers/history. Identity-
  matched immutable body content may remain cached; moved/deleted memberships
  and changed UIDVALIDITY are rechecked.

One proven invalidation edge case was fixed: two successful refreshes could share
the same wall-clock timestamp. Snapshot comparison now uses a fresh revision
identifier rather than timestamp equality. A regression freezes the clock,
removes a fixture UID, refreshes twice and proves membership/selection update.

No IMAP/SMTP connection lifecycle was changed. Existing read deadlines, bounded
retries, folder discovery, send state, Sent-copy and Trash deletion remain intact.
The database adapter retains short-lived connections, connection/statement
timeouts and the existing transaction-pool-compatible configuration. No unsafe
shared socket or new global connection pool was introduced.

## Measurements

`scripts/profile_communications.py` is an opt-in local profiler using actual
Streamlit AppTest pages/controllers, fake mail/Shopify providers and the disposable
loopback SQL fixture (`node tests/crm_postgres_server.mjs`). It is never imported
by the application. The fixtures do not use production credentials. Raw samples
are in `performance-evidence/before.json` and `after.json`.

For interactive local verification, with that SQL fixture running, use
`python tests/communications_preview_app.py --serve`, then open
`http://127.0.0.1:8510/?page=crm_campaigns_manage`. This is a test-only harness,
not an alternate production entry point. It blocks production connections and
records counters in `.venv/communications-browser-metrics.json`.

These are single local samples, not latency guarantees. Imports, scheduling and
local SQL timings vary. AppTest forces full-script runs even for fragment widget
events; real-browser fragment behavior was verified separately with counters.

| Path | Before | After | Relevant work |
| --- | ---: | ---: | --- |
| Campaign initial render | 422 ms | 628 ms | Reads 12 → 8; cold total did not improve in this sample |
| Campaign paste ~38 KB | 136 ms | 86 ms | Sanitizer calls 17 → 15 |
| Desktop → Mobile, AppTest full run | 374 ms | 129 ms | Reads 15 → 8; sanitizer calls 29 → 11 |
| Mobile → Desktop, AppTest full run | 333 ms | 174 ms | Same reduction; explicit second rerun removed |
| Campaign unchanged full rerun | 215 ms | 123 ms | Preview result reused; test preflight still runs |
| Canonical ~38 KB email assembly | 19.7 ms | 9.7 ms | Sanitizer calls 5 → 4 |
| Flow initial render | 285 ms | 223 ms | Six reads retained for initial truth |
| Flow first preview | 119 ms | 122 ms | Reads 6 → 5; one new render |
| Flow unchanged full rerun | 67 ms | 59 ms | Reads 6 → 5; sanitizer calls 1 → 0 |
| Flow mobile, AppTest full run | 91 ms | 55 ms | Reads 6 → 5; sanitizer calls 1 → 0 |
| Inbox initial controller + model | 3.54 ms | 3.33 ms | One discovery, list and selected body; no enrichment |
| Inbox cached model | 0.08 ms | 0.06 ms | No provider calls |
| Inbox refresh | 3.07 ms | 2.99 ms | Fresh discovery/list, no repeat body for matching identity |
| Inbox another selected body | 0.08 ms | 0.06 ms | One body fetch |
| Inbox explicit customer context | 0.18 ms | 0.15 ms | One enrichment lookup |

Inbox figures are fake-provider controller costs, **not real IMAP or customer DB
latency**. Remote image download/iframe paint time was not instrumented; browser
checks establish correct rendering and responsiveness, not a paint-time SLA.

In the running local browser, repeated Campaign Desktop/Mobile switches left
`full_page_runs`, `db_reads` and `preview_regenerations` unchanged (4 / 24 / 3).
Automation preview-width changes likewise left them unchanged (8 / 50 / 4).
Thus actual viewport-only events make **zero DB reads and zero new sanitizer /
plain-text generation calls**, unlike the AppTest full-run figures above.

## Feedback, invalidation and errors

Added restrained spinners for initial/return Inbox loading, notification-target
opening, Campaign settings/templates/open/save, Flow list/selected-email/save,
and cache-miss preview generation. Fast preview-cache hits do not show a spinner.
Existing mailbox component feedback (`Loading message…`, `Refreshing…`, `Working…`)
already covers selection, explicit refresh, folder actions and enrichment; it was
kept. No fake percentages, overlays or new layout/CSS were added.

Changing Body/Header/Footer, choosing another template, subject/preheader, market,
render settings or image mode changes the cache key immediately. Desktop/Mobile
does not. Saving, template mutations, archive/restore and test actions retain their
existing full reruns and fresh DB/permission/preflight checks. An older immutable
render may remain in the bounded LRU but can only be reused for identical inputs.
Recent campaigns and shared template choices therefore stay authoritative after
actions; no new stale database cache needs invalidation.

Audience calculation, version history, archives and reports remain explicitly
requested. All supported backend preview widths (600, 430, 390, 375, 320) remain.
Campaigns still exposes Desktop/Mobile; the existing Flow controls are unchanged.

Network failures, missing bodies/templates, invalid HTML and optimistic save
conflicts remain visible through existing handlers. Failed render results are not
cached, and spinners finish on exceptions. No real errors were silenced. Existing
Streamlit iframe/container deprecation warnings remain a future dependency-upgrade
task; changing the iframe API was deliberately kept outside this performance fix.

## Validation and scope

- CRM/Campaign/Flow/template/render/storage suites: **182 passed**.
- Email suites: **109 passed**.
- Support Email suites: **212 passed**.
- Navigation/startup/sidebar/social/analytics suites: **68 passed** (the initially
  skipped SQL-backed navigation check was rerun successfully with the fixture).
- Eight focused performance tests pass, included in the counts above: six preview
  cache/width contracts and two Email feedback/refresh tests.
- Nine JavaScript/component scripts pass: mailbox display cache, Trash menu and
  keyboard safety, send status, notifications, live/IDLE updates, connection status,
  compose/search focus and global search.
- Changed Python files compile; `git diff --check` passes.

Browser checks use the actual OS shell and Email/Campaign/Flow UI, with disposable
local SQL and fake provider boundaries. SMTP/IMAP connections, production database
connections and external requests are blocked in that harness. Checks include
1366×768, 1440×900 and 1920×1080; campaign source editing and simultaneous preview,
device switches, section accordions, draft save/reopen; Inbox default selection,
several message selections, refresh and folder return; Flow selection, preview
and unsaved trigger input. Screenshots in `performance-evidence` contain fixture
data only. Real-provider delays and customer data were not used to claim results.

Production modules changed: `crm_preview_cache.py`, `crm_html_workspace.py`,
`crm_campaign_content.py`, `crm_brand_template_ui.py`, `crm_campaign_page.py`,
`crm_flow_editor.py`, `support_email_logic.py`, `support_email_workspace.py`,
`support_email_page.py`. Supporting files: `scripts/profile_communications.py`,
`tests/test_crm_preview_performance.py`, `tests/test_email_loading_performance.py`,
`tests/communications_preview_app.py`, this report and its local evidence.

Email features, Campaign fields/content/footer/audience/test semantics, and
Automation triggers/timing/execution are unchanged. No schema, routing, CSS,
production configuration or unrelated module was changed. Marketing remains OFF.
No emails were sent, no live automation activated, and nothing was committed,
pushed or deployed. Safe for Nathan to test locally; external-service latency
should be observed during normal use before drawing production timing conclusions.
