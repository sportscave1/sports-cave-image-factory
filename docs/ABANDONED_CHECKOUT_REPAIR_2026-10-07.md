# Abandoned checkout repair — 7 October 2026

## Production diagnosis

Read-only investigation of the existing Render worker and private CRM database found nine durable manual enrollment requests stuck in QUEUED. The predicate `key >= 'checkout-enroll:' AND key < 'checkout-enroll;'` matched zero records under production collation, whereas `starts_with(key,'checkout-enroll:')` matched all nine. This prevented the enrollment worker claiming them and left the UI polling “Adding…”.

The background worker itself was running. The database contained 32 confirmed provider receipts and completed enrollments. The newest unsent automatic candidate was excluded by the existing marketing-consent rule. Other older rows predated the automatic-enrollment boundary. These are not evidence of failed SMTP delivery: marketing delivery uses Resend, independently of the support mailbox.

## Existing pipeline retained

`sports_cave_worker.py` supervises `crm_worker.py`. Its independent request processor polls every 2–5 seconds; the main leased engine runs with a 30-second wait between cycles. Actual cycle duration includes bounded external work. `sync_cache` maintains the Shopify Admin checkout mirror; native reconciliation uses fresh Shopify identity/consent, active flow rules, re-entry protection and the future-only cutoff. Eligible entries freeze the published steps and persist a UTC deadline. Engine advance enqueues one message per enrollment/step; database row leases and the unique idempotency key guard submission. Resend acceptance/provider identity is persisted before progression. Signed order events and fresh pre-send checkout validation stop recovered checkouts.

No browser, analytics popup or manual refresh is required for this pipeline.

## Changes and safety

- Replace collation-dependent lexical range with an exact prefix predicate.
- Reconcile committed membership after a lost request acknowledgement.
- Expire unprocessed manual intent after 15 minutes; at most three claims. Healthy in-flight leases remain protected. Explicit Retry performs fresh validation through the existing path.
- Resolve a UI persistence wait after 30 seconds and read the durable request/membership. No UI enrollment or send calls were added.
- Keep the automatic cutoff (`checkout-auto-start-v2`, production 2026-10-05 22:59:03 UTC) and activation boundary unchanged. Historical rows do not automatically become eligible.
- At deployment the nine old requests should resolve to one acknowledged existing membership and eight expired requests. Expiring requests does not enroll, send, delete history or change consent.
- Cap explicit provider rate-limit rejection retries at five attempts, five minutes apart. Pre-submission retries retain existing limits. Ambiguous post-submission timeouts/crashes remain UNCERTAIN, never silently replayed; delivery must be reconciled before any resend.
- Skip malformed checkout identities during mirror pagination, record safe counters and continue later valid rows. Infrastructure exceptions still fail the page for retry.
- Display explicit consent/historical/awaiting-check states and calculate countdowns from the current clock against the persisted deadline.
- Enable safe sync/worker cycle, due-count, eligibility-reason and stale-request reconciliation logs. No email content or credentials logged.

No Shopify data, consent rules, flow timing configuration, provider contract, schema or Render topology changes.

## Validation

Local PGlite PostgreSQL tests with fake Shopify and mail transport: 118 tests, 117 passed; one unchanged baseline failure expects 20 CRM tables but the current migrations create 24. Baseline reproduction confirmed the same failure. Five UI reducer tests pass, including lost acknowledgements and bounded pending state; timing tests cover historical/consent labels and advancing countdowns.

New acceptance coverage exercises automatic entry and deterministic due time without a UI, one send, future-step recovery, later-arriving email, historical request expiry without a batch, disjoint claims, restart/lease recovery, lost acknowledgements, malformed mirror rows, bounded rate limiting and no replay of ambiguous submissions. Existing provider/concurrency/automation tests retain their safety assertions.

The older `test_crm_checkout_reliability` / `test_crm_automation_analytics` run has ten failures and one error on the untouched baseline (legacy timing, old source/cursor mocks and future-dated send fixtures). They are reported separately, not presented as passing or changed to conceal failures.

Python compilation and `git diff --check` pass. Render topology validator passes; no Blueprint changes are necessary. Browser and production verification are recorded in the task's final report. No test messages are sent to customers.
