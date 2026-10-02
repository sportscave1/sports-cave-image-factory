# Campaigns Home redesign

## Files changed

Production UI/navigation:

- `app.py` (one routing-source argument)
- `crm_navigation.py`
- `crm_campaign_page.py`
- `crm_campaign_home.py` (new)
- `crm_campaign_home_data.py` (new read-only projections)
- `crm_campaign_progress_ui.py`
- `crm_campaign_analytics_ui.py`

Tests/evidence:

- `tests/test_crm_campaign_home.py` (new)
- `tests/test_crm_campaign_home_ui.cjs` (new)
- `tests/fixtures/campaign_home_preview.py` (new)
- `tests/test_crm_campaign_first_paint.py`
- `tests/test_crm_campaign_loading.py`
- `tests/test_crm_campaign_history.py`
- `tests/test_crm_production_v2.py`
- `tests/test_crm_send_progress.py`
- `tests/test_crm_ui.py`
- `tests/test_campaign_recovery.py`
- This report: `docs/CAMPAIGNS_HOME.md`

## Runtime and navigation

Active route: OS sidebar → `app.set_current_page()` → `crm_page.render_page()` →
`crm_page._render_page()` → `crm_campaign_page.campaign_workspace()`.

The workspace uses one `campaign_view` state: `CAMPAIGNS_HOME` or
`CAMPAIGN_EDITOR`. Home is the initial default. An explicit `campaign` URL opens
the existing editor. Sidebar entry requests Home; browser-history navigation
preserves deep links. Clicking the Campaigns sidebar item while editing uses the
same existing dirty-state leave dialog as the restrained “← Campaigns” action.

Home calls `crm_campaign_home.home()`. New/Edit/Duplicate still use
`new_compose()`, `open_editor()`, the existing draft store, and existing recovery
protections. Templates opens a new normal composer with its existing Templates
tab selected. Sent campaigns still pass the existing durable delivery lookup and
open `operational_view()`, bypassing authoring and send controls.

The old embedded Active/Sent list implementation was removed. `recent_campaigns()`
is only a compatibility entry point to Home. No list is appended to the editor.
Existing detailed analytics and version history remain explicit actions.

## Presentation

The global shell is unchanged. Home adds the breadcrumb, title/subtitle, gold New
action, five compact KPIs, All/Drafts/Active/Sent/Archived controls, search, market
and status filters, default newest-first sorting, performance rows, Quick Actions,
top-performer rail, and subdued template banner.

On wide screens, toolbar controls share a row and the rail sits beside the main
content. At 1500px and below, the rail and toolbar groups stack rather than squeeze.
KPIs use five columns on wide desktop, three at medium widths and two below 700px.
Only the table has horizontal scrolling when necessary; the page stays contained.
Status includes readable text. Native menus retain keyboard access and descriptive
help. Campaign titles also link to their existing campaign URL.

No mock reference numbers are present in production code. No new help card was
added because a suitable existing guide destination was not established. Missing
thumbnails use a lightweight SC mark. Existing `picker_thumbnail()` produces 80px
Shopify CDN URLs; images are lazy-loaded, contain rather than crop, and have ALT.

## Data definitions

All data comes from local persisted CRM tables. No Shopify/Resend call is needed.

| KPI | Source and definition |
| --- | --- |
| Active | Non-archived drafts joined to a production campaign whose status is not SENT; drafts without a production record have a separate Drafts tab. |
| Sent (30 days) | Non-test `crm_marketing_sends` with ACCEPTED status and `first_submitted_at` within 30 days, belonging to a production campaign. This counts provider submissions, not deliveries. |
| Revenue (30 days) | Eligible `crm_order_attribution.amount`, with `order_created_at` within 30 days; amounts grouped and displayed by currency, never converted or summed across currencies. |
| Click rate (avg · 30 days) | Average of per-campaign unique delivered-and-clicked recipient counts divided by unique delivered recipients, for campaigns SENT within 30 days. Campaigns without delivered evidence do not contribute a fabricated rate. |
| Orders from email (30 days) | Eligible persisted attribution rows whose order timestamp is within 30 days. |

Empty/unavailable revenue and rates show “—”. Known empty counts show zero.
Missing draft delivery metrics show “—”, not invented delivery counts.

| Table field | Source |
| --- | --- |
| Name / subject / market / thumbnail | Draft metadata; only subject, market and the first visible Catalogue product image URL are extracted from its document. |
| Updated | Greatest draft/campaign update timestamp, displayed in UTC. |
| Recipients | Existing final recipient count, with planned non-test send-row count as fallback, matching Sent reporting. |
| Delivered | Unique recipient send rows with delivery evidence. |
| Opened / clicked | Unique delivered recipients with corresponding events, matching existing Sent-report semantics. Repeated webhook events do not multiply counts. |
| Orders / revenue | Eligible persisted attribution for that campaign, all time; currency-separated totals. |
| Status | Archive metadata takes precedence; otherwise durable production status or authoring status. |

Top performer is a SENT, non-archived campaign with the most eligible attributed
orders, with sent timestamp/ID as deterministic ties. The card explicitly says
“Ranked by attributed orders · all time.” There is no AI score or cross-currency
revenue comparison. Without eligible attribution, it shows “No performance data yet.”

## Loading, query budget and cache

One Home fragment owns every placeholder it later replaces. Header, controls,
KPI shells, table headings and rail are emitted before reads start. A two-thread
executor runs independent totals and list reads. An eight-job admission bound
prevents uncontrolled queues. Workers only read data; they do not access Streamlit
state or UI. One failed totals projection does not prevent the list from rendering.

A cold Home load performs exactly three SQL statements:

1. Global counts and the 30-day KPI aggregate.
2. Top-performer ID aggregate.
3. Paginated metadata with batched delivery and attribution aggregates.

The page displays 12 campaigns, reads one lookahead row, and can additionally
include the top performer and an explicitly requested analytics campaign. Subject
and thumbnail extraction happen only for these selected rows. No full documents,
HTML, templates, recipient lists or detailed event streams are returned. There are
no per-row application queries; only explicit History/Results actions load details.
An already-active send tray may independently make its existing cached batch
progress read; application login/shell queries are outside this Home budget.

Session-scoped future/results entries have a 20-second TTL and an eight-entry
bound. Identical in-flight requests coalesce. Filters use separate bounded keys;
unchanged totals can be reused. Returning from the editor, opening/duplicating a
campaign, archive/restore/delete and analytics closure invalidate Home data.
No stale in-flight future can repopulate a cleared cache. Polling is native and
fragment-scoped; it suspends once an analytics/delete dialog owns the UI.

The old page synchronously restored/configured/rendered a full composer before
loading its history. Home avoids all that work. The prior list did not have an
application-level metrics N+1; this redesign preserves that property with joined
aggregates. No production latency or speedup percentage is claimed.

Synthetic loopback SQL measurements during development: summary 27.68ms, top ID
12.45ms, paginated projection 23.24ms. These are disposable PGlite/RPC measurements,
not Supabase/Shopify/production timings. Safe logs record only fixed stage names
and durations, never campaign copy, PII, tokens or query parameters.

## Safety and verification

No send/audience/consent/suppression/transport/rendering/tracking/attribution/
scheduling/idempotency implementation or schema was changed. Existing analytics
UI changes only invalidate Home data on close. Delivery UI changes only route Back
and View analytics to the new Home location.

Offline tests cover Home defaults, records, New/Edit/Duplicate targeting, existing
Templates UI, dirty navigation, explicit campaign URLs, browser-history distinction,
mutually exclusive views, local async reads/cache invalidation, bounded queries,
unchanged analytics semantics, duplicate events, eligible/ineligible attribution,
currency handling, HTML escaping and thumbnail URLs. Existing editor/review/send/
size/idempotency/recovery suites are also run.

The browser fixture uses the actual sidebar and Home renderer with synthetic
records. All non-loopback browser traffic is blocked. Browser checks cover 1920×1080,
1366×768, 750×900 and 390×844, KPI columns, rail placement, document containment and
absence of Streamlit errors. Screenshots are evidence of local rendering, not
production data or a claim of pixel-identical browser behavior.

Two pre-existing leave-dialog AppTest assertions retain old dialog buttons after
navigation. Both reproduce using the original HEAD Campaigns page; their database
persistence and route assertions pass. The new Back Cancel/Discard tests pass.

No commits, pushes, deployments, live email, production writes, migrations,
environment changes or Render changes were performed.

Final results: the main batch passed 177 tests, an additional fresh-database
production-campaign batch passed 27 tests, and final Home rechecks passed 12 tests
(overlapping the main batch, plus the new failed-totals isolation test). Browser
checks passed all four viewport cases; existing send-status timer checks passed.
Python compilation and `git diff --check` passed. The two baseline leave-dialog
assertion failures above remain explicitly documented rather than silently omitted.

Ready for deployment based on this offline validation. Production latency and
production screenshots were not measured.
