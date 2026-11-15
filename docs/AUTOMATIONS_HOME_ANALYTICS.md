# Automations overview and activity

Home renders independent, bounded jobs for counts, period summaries, activity,
and the selected table page. It retains last-good results during refresh/errors.
Search, trigger and sort changes replace only the table query. Shopify customer
labels are an optional cached batch, never a prerequisite for rendering Home.

## Metric definitions

- Active: current, non-deleted/non-archived ACTIVE definitions.
- Sent: accepted, non-test automation messages submitted in the rolling UTC
  `[now - 30 days, now)` window.
- Delivery: distinct delivered messages / accepted messages.
- Open: distinct delivered-and-opened messages / delivered messages.
- Click: the existing mean of per-flow delivered-and-clicked / delivered rates.
- Revenue: eligible canonical order attribution with automation evidence,
  ordered in the same period, grouped by original currency. No currency mixing.
- Comparisons: the immediately preceding rolling 30-day period. No historical
  Active count is available, so that card has no invented trend.
- Overview rows retain existing lifetime flow totals; analytics charts and
  summary cards explicitly use the rolling period.

## Checkout analytics and manual entry

Analytics opens a paginated Shopify abandoned-checkout list (25 per page), then
overlays the signed token ledger, exact flow enrollment, send receipts and
verified delivery events. Contact information remains an authenticated Shopify
read; it is not copied into new database fields.

The selected countdown ticks locally each second. Backend state refreshes every
20 seconds while checkout analytics is open; Shopify responses reuse the
existing 60-second cache. Pause/recovery/completion override pending countdowns.
Between provider acceptance and cursor advancement, the next countdown uses
the same runtime formula: accepted receipt `updated_at` + next frozen step delay.
An accepted last email is shown as awaiting completion until the worker records
the final journey state.

Add to flow requires explicit confirmation and manage permission, an active
published native flow, current backend readiness, fresh exact Shopify checkout,
matching signed customer/token receipt, current consent/suppression eligibility,
flow rules, and elapsed inactivity. Checkouts predating activation remain
blocked; this is not a historical backfill feature. Fresh Shopify activity also
blocks premature entry. Runtime locks recheck the ledger timer and recovery.
The existing trigger key/reentry guard prevents duplicate enrollment across
versions. This action never submits an email inline; existing background
delivery and recovery suppression remain authoritative.

Duplicate creates an unpublished draft, including for legacy flows. Archive uses
the existing pause/archive lifecycle. Delete is a tombstone available only for
draft/archived flows, preserving journey/send/event history.

The frontend diagnostic panel is removed. Worker readiness refresh and publish/
enrollment guards remain in the backend.

## Release verification

Apply `20261005145500_crm_automation_reporting_indexes.sql` through the reviewed
migration runner before release. Its six idempotent indexes change no data or
RLS policies. No new tables/columns, Render variables or webhook registrations
are required. Local tests apply the migration only to disposable PostgreSQL.

Local validation: focused automation, preview, trigger, Campaign Home/cache and
migration regression tests; GraphQL schema validation; browser action/editor and
overflow checks at 1920, 1366, 750, 390 and 320 pixels; Python compilation and
diff whitespace checks. Browser fixtures block external provider requests.

Production Shopify permissions, event freshness, real attribution and worker
handoff still need authenticated release verification. No live email, automation
publication, Shopify mutation or deployment is performed by this change.
