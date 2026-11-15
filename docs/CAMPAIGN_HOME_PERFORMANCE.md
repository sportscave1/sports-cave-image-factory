# Campaigns Home: local data-flow and performance repair

## Confirmed causes

The implementation is a Python Streamlit route with server-side fragments. It
has no custom React fetching hooks or Strict Mode loader in this repository.

The previous Home fragment first emitted `kpis()` without data on every rerun,
then replaced that HTML after examining its future. It similarly emptied and
rebuilt the table placeholder. A cached response therefore still passed through
an unresolved visual frame. Its summary exception handler explicitly replaced
resolved numbers with empty cards. Search, tabs, sort and the polling button all
reran that same fragment. Polling additionally issued an explicit fragment rerun
after the native widget event had already caused one.

The eight-entry cache cleared **all** entries when full, including summary and
in-flight tab jobs. Its TTL started at submission rather than completion. This
could restart a slow response immediately. It stored no independent last-good
payload. These are code-confirmed reset paths; no production timings were taken.

Each listing refresh also queried the all-time attributed-order top performer
before the bounded list query. The rail narrowed the table, while the table
forced minimum widths of 970/1045px. This caused overflow even when the page
itself remained contained. At 1366px the previous KPI grid also used two rows.

## Authoritative sources and definitions

| Display | Existing authority |
| --- | --- |
| Drafts, archive state, definitions, subject, saved thumbnail | `crm_campaign_drafts` |
| Send state, send time, final recipient count | Immutable campaign/send records in `crm_campaigns` |
| Active KPI and status counts | Existing app categories: unarchived non-SENT delivery campaigns are Active; unarchived drafts with no delivery are Drafts |
| Sent emails | Non-test `crm_marketing_sends` with provider-accepted status and `first_submitted_at` in the period |
| Delivered/opened/clicked | Verified Resend event facts in `crm_delivery_events`, matched to those production send IDs; each recipient counts once |
| Click rate KPI | Existing mean of campaign unique-recipient click rates for campaigns sent in the period; clicked-and-delivered / delivered, not total click events |
| Orders/revenue | Existing eligible Shopify-derived `crm_order_attribution`, retaining separate currency totals |

This application sends individual provider emails, not a provider-owned campaign
broadcast whose summary could replace these records in a single API call. Resend
webhook facts and the existing Shopify attribution ledger are the authoritative
app reporting sources already used by `crm_campaign_analytics`. Home makes zero
Shopify or Resend API calls and loads no recipient profiles or message bodies.
This deliberately retains canonical persisted app records, which the requested
source rules allow. A live provider-console comparison was not performed.

Every summary refresh captures one UTC half-open `[as_of - 30 days, as_of)`
window. Sent uses submission time; click rate uses campaign sent time; eligible
orders/revenue use order-created time. The same start/end parameters are passed
to both period queries. The table retains campaign-lifetime reporting. Unknown
currency/undefined click denominators remain `—`; no invented currency, revenue,
trend or fake production row is introduced.

## New request and state flow

Header and controls emit without waiting for reads. Four bounded executor jobs
may run concurrently: counts, delivery summary, attribution summary, visible
table. The executor has four workers and a global twelve-job admission limit.
The initial All table is the only requested status view. Counts do not load the
other tabs' datasets. The table returns at most thirteen page rows (twelve plus
the next-page probe), with an optional specifically opened analytics row.

Counts, delivery and attribution fail independently. Attribution's orders and
currency sums now share one filtered aggregate instead of scanning that period
twice. There is no eager all-time top-performer query, rail, or history/detail
fetch. Existing per-row duplicate, archive, restore, history, delete and results
actions remain, with details loaded only after those actions.

Summary and table fragments handle their own controls. Search/filter/sort do not
invalidate KPI jobs. Completed tab/filter/page results are reused for the
20-second TTL; pending reads deduplicate. A 24-entry session cache evicts only
completed non-summary entries and protects KPI results. Last-good payloads are
stored separately, bounded, and retained across invalidation and refresh errors.
Only the currently registered future can publish; worker threads do not mutate
Streamlit state. Missing/partial summary responses cannot replace resolved facts.
A valid empty table or complete zero-valued summary is still authoritative.

The explicit states are UNRESOLVED, LOADING, READY, REFRESHING and ERROR. KPI
skeletons appear only while a field has never resolved. READY values remain
visible throughout REFRESHING and ERROR, with compact retry text.

Browser testing exposed collisions when two sibling polling buttons fired
together. The final design has one parent-owned native refresh button, with
one-shot scheduling after a completed render. Children can accelerate that
controller when a new read starts; they never mutate its external Streamlit
container. There is no second explicit rerun after the native poll event. Pending
reads poll at 250ms, otherwise 20 seconds. Polling pauses during dialogs and stops
when Home unmounts. Periodic parent refreshes emit the child regions using cached
payloads; ordinary search/tab interactions target only the table fragment.

## UI and evidence

Scoped Home styles provide a 24px header gutter in the local OS-shell fixture,
five restrained KPI cards across at 1366/1920px, fixed Lucide-style line icons,
gold-underlined native text controls without radio inputs, and a full-width list.
There are no forced table minimum widths, fixed table heights, internal vertical
scrollbars, large promotion panel, or empty top-performer card. Secondary columns
collapse based on available table width; phone rows retain identity, market,
status, compact delivered/clicked context and actions. Real thumbnail URLs are
lazy-loaded with explicit dimensions. Actions have descriptive accessible names.

`tests/test_crm_campaign_home_ui.cjs` blocks all non-loopback browser traffic and
checks 1920, 1366, 750, 390 and 320px. It checks overflow, internal scrollbars,
active gold tabs, icon rendering, control widths, unchanged KPIs during search,
and a delayed-read / delivery-outage scenario. The fixture is visibly synthetic
and is not production fallback data.

One recorded final-controller run: shell 1119ms, visible rows 1990ms, all KPI groups 3245ms.
The fixture deliberately delays counts 500ms, delivery 1400ms, attribution 2200ms,
and rows 800ms. These totals also include local Streamlit startup and OS-shell
fixture work. They prove progressive rendering and stability, not live latency.

`python -m tests.benchmark_crm_campaign_home` compares the original checked-in
query scheduling with the new scheduler using equal fabricated 80ms read latency:
the visible-table median was 160.9ms before and 80.7ms after. Cold SQL request
count changes from three coupled reads to four independent reads. A table change
uses one read instead of two; a cached tab revisit uses zero. Neither comparison
claims production speed. `campaign-home-profile.json` contains local measurements
and EXPLAIN ANALYZE plan summaries from the disposable loopback PostgreSQL fixture.

## Limits and validation

Real SQL tests compare projected numbers with the existing campaign reporting,
including duplicate webhook events, ineligible attribution and orders older than
30 days. Cache tests cover late responses, partial payloads, independent errors,
in-flight deduplication, bounded eviction, summary protection and tab revisits.
Campaign navigation, dirty-state protection, send/idempotency, compact review,
preview, first-paint and email-size regressions are also run offline.

No production database/provider was contacted. Exact counts still require
canonical metadata counts; period aggregation still depends on the existing
database indexes, and a date filter does not guarantee a physical range scan.
The local small fixture's plan is not evidence of production-scale query cost.
Persisted delivery/attribution figures also depend on backend webhook/reconcile
freshness. Large-history latency, deployed CSP/icon behaviour and actual live
provider agreement still need a production smoke check after an authorized deploy.
No schema, migration, sending, tracking, attribution or worker behaviour changed.

Final local validation: 135 Python tests passed across campaign Home/cache,
first-paint, send flow, email size, fast review, review modal, send progress,
CRM UI and preview-performance suites. Five browser viewports and the delayed-read
refresh/outage checks passed. Changed Python files compiled successfully and
`git diff --check` passed. No tests used live Shopify/Resend transport.
