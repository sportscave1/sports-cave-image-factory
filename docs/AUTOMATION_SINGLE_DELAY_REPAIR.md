# Automation scheduling repair — 6 October 2026

## Findings and production inspection (read-only)

The existing `sports-cave-seo-worker` runs `sports_cave_worker.py`, which supervises `crm_worker.py`. CRM polls every 30 seconds, with persisted Supabase state. No browser needs to remain open. No additional Render service is needed.

Production was not showing a current sending outage at inspection: the active abandoned flow had 31 completed enrolments, 31 provider-accepted sends, zero active/due enrolments and zero missing deadlines. The worker heartbeat was healthy. These were existing production sends, not test sends initiated by this repair. A prior individual missed send cannot be attributed conclusively from that snapshot.

Concrete reliability defects addressed:
- Abandoned enrolment previously performed a second Shopify catalogue scan in addition to the working mirror sync. Source/reconciliation work preceded due delivery and could delay it.
- Qualification and email delay were separate waits, despite appearing to describe one delay.
- Verification retries changed the actual next-send deadline, mixing retry backoff with scheduling.
- Analytics predicted the next step locally instead of using the persisted worker schedule.
- Queue claiming did not explicitly require the enrolment's current step and persisted deadline to match the job.

Marketing/provider/sender configuration and abandoned/post-purchase capabilities were available. Welcome and fulfilled capabilities reported missing `CUSTOMERS_EMAIL_MARKETING_CONSENT_UPDATE` and `ORDERS_FULFILLED`, respectively. Those flows were not active. Configure those subscriptions and verify capability before activating those triggers. No secret values were inspected or printed in this report.

## Final path and timing

Shopify webhook / existing paginated abandoned-checkout mirror sync → Supabase checkout/event → bounded, freshly verified eligibility candidates → persistent enrolment with frozen steps and `trigger_at` → `next_due_at` → existing background CRM worker → unique shared send job with `due_at` → atomic leased claim → fresh safety checks → Resend acceptance → persisted accepted receipt → next step/recovery reconciliation.

`next_due_at` is the existing schema's scheduled-send timestamp; there is no second competing `scheduled_send_at` column. First deadline = verified trigger/activity time + Delay. Later steps = previous accepted receipt timestamp + that step's Delay. Historical manually enrolled checkouts may already be due. Automatic enrolment remains bounded by activation and the persisted automatic-start boundary; neither repair nor page load enrols history.

Legacy definitions are normalized idempotently at editor/save/publication boundaries, with compatibility for still-published legacy flows. 30 minutes qualification + 1 minute first-step delay becomes 31 minutes. Only the first step changes; subsequent delays stay independent. Published definitions carry timing version 2. Existing frozen enrolments and non-null deadlines are not rewritten. Opening the editor preserves non-minute legacy values exactly until deliberately edited.

Atomic claiming uses PostgreSQL `FOR UPDATE SKIP LOCKED` plus a conditional lease-token update. Unique per-enrolment/per-step keys and provider idempotency prevent normal duplicate submissions. Ambiguous submissions remain held as UNCERTAIN rather than automatically replayed; no distributed provider system can promise unconditional exactly-once delivery across unknown network outcomes.

Fresh consent, local/provider suppressions, active flow, current step, checkout recipient identity and recovery are rechecked. Recovery/pause are checked again at the locked submission boundary. Provider acceptance alone persists successful send; queue creation is not success.

Analytics uses the same `next_due_at`, with a display timestamp frozen until load/refresh/data change. It does not poll for countdown ticks. A step awaiting the worker's next schedule says Awaiting schedule rather than inventing a deadline.

## Additive migration and deployment order

Apply `migrations/20261006033000_crm_single_delay.sql` before starting the updated application/worker. It adds `retry_after`, due/candidate indexes, and idempotently repairs only null native deadlines with trustworthy frozen timing/previous accepted receipt evidence. It never sends, enrols, deletes history or moves an existing deadline. The current schema already requires a non-null deadline; the null repair also supports older nullable schemas. Production inspection found no rows requiring that backfill.

No new Render worker, cron, environment variable or abandoned-checkout webhook is required. No deployment or production migration was performed. Unrelated dirty repository changes were preserved; this report does not approve deploying those changes.

## Files touched for this task

- crm_automation_timing.py (new)
- crm_automation_definition.py
- crm_automation_store.py
- crm_automation_publication.py
- crm_automation_ui.py
- crm_automation_runtime.py
- crm_checkout_analytics.py
- crm_engine.py
- crm_store.py
- crm_checkout_timing_ui.py
- crm_automation_analytics_ui.py
- crm_automation_home.py
- migrations/20261006033000_crm_single_delay.sql (new)
- tests/crm_postgres_server.mjs
- tests/test_crm_automation_timing.py (new)
- tests/test_crm_native_automations.py
- tests/test_crm_shopify_automation_triggers.py
- tests/test_crm_checkout_timing_ui.py
- tests/test_crm_automation_ui.py
- tests/test_crm_automation_ui.cjs
- docs/AUTOMATION_SINGLE_DELAY_REPAIR.md (this report)

## Validation

Disposable loopback PostgreSQL fixture: `node tests/crm_postgres_server.mjs`.
With `CRM_TEST_POSTGRES=1`:

```
.venv/Scripts/python.exe -X utf8 -m unittest tests.test_crm_native_automations tests.test_crm_shopify_automation_triggers tests.test_crm_checkout_analytics tests.test_crm_automation_ui tests.test_crm_checkout_timing_ui tests.test_crm_automation_timing tests.test_crm_send_flow tests.test_crm_automation_publication tests.test_crm_abandoned_checkout -q
```

142 tests passed. Covers schedule arithmetic, delay migration, no pre-due send, persistence/restart, unique queue creation, two claimers, chained steps, pause/reentry/consent/suppression/recovery, missing-deadline repair, sync compatibility, publication and mocked transport. Local database adapter serializes transactions; the two-claimer test verifies one returned claim, not a real multi-host load test.

`node tests/test_crm_automation_ui.cjs`: passed with external requests blocked, five viewport widths (320–1920px), Analytics, single Delay control, editor, multi-email actions, and overflow checks. Python compile checks passed for all changed application modules.

No real customer email, provider write, production data mutation, commit, push or deployment occurred.
