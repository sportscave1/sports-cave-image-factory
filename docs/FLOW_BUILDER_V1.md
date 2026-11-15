# Sports Cave OS Flow Builder V1

The existing Automations overview, six summary cards, filters, table columns,
navigation and action menu are retained. Open editor and the existing Create
automation action now open the sequence editor over that page. Email content,
templates, preview and internal testing still use the shared composer.

## Data and delivery

- Existing automation IDs, enrollment IDs, template versions, sends and provider
  events are retained. The exact legacy display name “Abandoned Checkout —
  Reminder 1” is shown as “Abandoned Checkout Recovery”; this does not create or
  migrate a record. The current email remains Email 1.
- Steps have stable UUIDs and optional names/enabled flags in the existing draft
  JSON. Old definitions default to enabled. Reordering never changes a step ID;
  duplication creates a new ID. There is no application step-count limit.
- New checkout drafts start with three editable reminders at 2 hours, 24 hours
  and 48 hours. Existing flows are not expanded automatically.
- Publication omits disabled steps from the new sequence, retaining draft content
  and previous template versions. Existing enrollments keep their complete frozen
  sequence, even after a later publication removes a step or changes its trigger.
- The existing CRM worker, database queue, atomic leases and provider idempotency
  keys remain authoritative. Saved drafts and simulation do not enroll or send.
- The initial wait is relative to the trigger. Subsequent waits start from the
  preceding enabled email's provider acceptance. Smart Sending may defer a short
  interval; it does not discard the remainder of the flow. Provider acceptance
  is reported separately from delivery events.
- Pause blocks entry and submission. Resume preserves remaining waits and spreads
  already-overdue enrollments in groups of five per 30 seconds. The existing
  provider pacing and validation continue to apply.
- Known rejections can be explicitly retried from recipient activity using the
  original receipt and idempotency key. Accepted or uncertain submissions cannot
  be retried through that action. Rate limits have a bounded retry path. Every
  retry rechecks current eligibility; purchase/opt-out exits remain mandatory.
- The previously implemented historical checkout action remains one click, with
  immediate first-step dispatch through the existing manual-request worker lane.
  Publication never automatically backfills historical checkouts.

## Triggers and setup

Checkout abandoned, email subscription, order paid and fulfillment use existing
Shopify ingestion. Win Back now uses the existing paginated customer/last-order
reader with configurable inactivity days and stable customer/order deduplication.
Its scan is bounded to one page, with a five-minute pause between completed scans.
Shopify capability verification is still required before publishing and sending.

Identifiable abandoned-cart events are not available in this integration; the UI
does not advertise cart recovery as operational. No new integration is installed.
The timing tab warns that external Shopify/marketing-platform sends are not
visible to this ledger and must not duplicate the configured recovery sequence.

## Analytics and testing

Activity reuses send, delivery-event and attributed-order ledgers. It adds per-step
queued/sent/delivered/opened/clicked/bounced/failed/skipped counts, delivery rate,
published delays, enrollment schedules, recipient timelines, safe retry controls
and the existing worker heartbeat. Revenue uses existing reliable attribution.
An un-attributed unsubscribe is not invented as a per-email metric.

Test Flow evaluates synthetic entry rules, consent/purchase exits, later opt-out,
enabled order and planned times without touching enrollments or sending. Verified
internal email tests remain in the existing composer.

Tests use an isolated local SQL fixture, mocked Shopify/provider calls and a
loopback-only browser. They include 32 preserved historical receipts, version
editing, steps, timing, automatic/manual entry, consent/purchase exits, claim
contention, retries, pause/resume, analytics and desktop/mobile editor behavior.
No production data or customer email is used.

## Deployment

No database migration, dependency, separate scheduler, service or Blueprint change
is required. Deploy the application and existing CRM worker from the same revision
through the normal workflow. The worker retains its 30-second cycle and existing
2–5 second manual enrollment lane. Existing delivery enablement, sender, provider,
webhook and Shopify capability settings remain required. Development did not
deploy, publish a production flow or send customer email.

## Files

- `crm_flow_builder.py`: modal sequence/settings/activity controls and pure simulation.
- `crm_automation_ui.py`: existing editor routing, shared composer and publish confirmation.
- `crm_automation_definition.py`: compatible step metadata and inactivity/exit settings.
- `crm_automation_store.py`: new-flow defaults, safe retries, resume pacing.
- `crm_automation_publication.py`: enabled-step snapshots and frozen exit settings.
- `crm_automation_runtime.py`: native Win Back reconciliation.
- `crm_engine.py`: immutable sequence validation, frequency deferral, retry error detail.
- `crm_store.py`: recheck rescheduled deadlines at the submission boundary.
- `crm_automation_capabilities.py`: Win Back readiness using existing scopes/events.
- `crm_automation_home.py`, `crm_automation_home_data.py`: preserved overview with display alias, step counts and extended metrics.
- `crm_automation_analytics_ui.py`: on-demand per-email scheduling/performance extension.
- `tests/test_crm_flow_builder.py`, `tests/test_crm_native_automations.py`, `tests/test_crm_automation_ui.py`, `tests/test_crm_flow_builder_ui.cjs`: regression coverage.
- `tests/fixtures/crm_automation_preview.py`: isolated browser-run fixture identities.

Rollback requires the prior application revision, not destructive data changes.
After new step metadata has been saved, older validators that reject additional
JSON fields should not be used to edit those drafts; retain this compatible
definition validator when rolling back presentation changes.
