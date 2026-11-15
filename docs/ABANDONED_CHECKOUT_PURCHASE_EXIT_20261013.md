# Abandoned Checkout newer-purchase exit — 13 October 2026

Implemented locally in task 20261011-54d8ff88; no commit, deployment, production update, activation or email send. No further Post Purchase content/settings changes were made.

## Confirmed case and root cause

Read-only checks in the documented authoritative Supabase project and existing Render worker logs confirmed Noelene Faulks's #SC3282:

- Order gid://shopify/Order/18941038035251 belongs to customer gid://shopify/Customer/31290256884019; PAID, not cancelled. Signed orders/paid event 49957112-e5b1-4af1-813e-379abd116400 occurred **13 October at 9:45:21 am AEDT**.
- Checkout created **9:08:04 am** has exact recovery key beginning 6b73a02e and correctly references this order. Its checkout is RECOVERED, without an automation journey.
- Different checkout created **9:25:03 am**, key beginning 7edac4f3, remains ABANDONED. Journey **9083971b-407b-4912-ba0e-6f065a03f319** is ACTIVE with verification_unavailable, persisted due **11:25:03 am**, repeated five-minute retries and zero accepted receipts.
- There were **zero accepted Abandoned Checkout emails before payment** for this customer. Attribution is already **NO_MATCH / eligible=false / AUD 339.00**. No recovered email revenue should be added.

Signed order events were hashed/matched only to their exact checkout key. Engine.validate's customer-wide newer-order check applied only to no-key legacy journeys or manual-checkout journeys, after Shopify checkout verification. The native token-bound second journey skipped that check; a ValueError in verification prevented reaching any independent purchase exit. The progress projection consequently kept displaying a countdown/Due.

Production logs confirm recurring ValueError but retain only its class, not the underlying message. The precise upstream failure cannot be retrospectively distinguished between unavailable checkout details, product pagination/identity errors or another validation failure from those logs. The fix honors independent signed payment evidence before all such reads and adds allowlisted verification codes for future investigation, without logging raw errors, provider bodies or personal data. Unrelated genuinely unverifiable checkouts continue failing closed.

## Implementation

- New crm_checkout_purchase_exit.py reads HMAC-verified Shopify inbox facts: paid topic, same Shopify customer and shop, supported payload version, payment occurrence strictly after checkout creation and not in the future. It excludes signed cancelled/voided/refunded order evidence. Receipt time, lastOrder alone, emails/names and guessed checkout associations cannot authorize an exit.
- A verified newer purchase sets only the active journey to **STOPPED / NEWER_PAID_ORDER**, clears verification retries and blocks PENDING/CLAIMED sends only when they have neither a submission timestamp nor provider receipt. The historical next_due_at remains retained because the schema requires it; STOPPED status removes it from scheduling/countdowns. SUBMITTING, UNCERTAIN and ACCEPTED receipts remain unchanged. Cancellation after stopping never automatically reopens reminders.
- Checks run before overdue advancement/retry and fresh checkout/customer lookup, during paid-event processing, before native enrollment and again inside the final submission transaction. Signed paid events with no checkout token now use the same existing durable ingestion path. Customer advisory locks precede automation/journey/checkout locks in enrollment/submission; ingestion uses the same guard, serializing different-token payment evidence with submission without adding infrastructure.
- Exact recovery matching and checkout.order_id/completed_at/status evidence remain unchanged. The separate purchase exit never attaches the paid order to the unrelated checkout and never writes attribution/revenue records.
- The single bounded progress read projects the same signed proof using an indexed EXISTS query. Unsent stages display **Purchased — reminders stopped**, even before an old worker has reconciled the journey; accepted stages retain their receipt status. Exact checkout recovery displays Recovered only with conversion evidence. Existing revenue calculations still require eligible attribution.
- The visible abandonment date now includes local time, e.g. **13 Oct · 9:25 am**. Full timestamp and timezone remain in the tooltip. No templates, schedules, tracking, provider configuration or delivery consent/suppression/unsubscribe gates were changed.
- Read-only EXPLAIN for the production customer/payment lookup uses the existing crm_lifecycle_order_event index. No schema/index migration or production DDL was needed.

## Tests and evidence

- **232 Python tests passed, zero failures/errors/skips**, on fresh disposable PGlite PostgreSQL with actual repository SQL/migrations and synthetic Shopify/provider facts; 85.538 seconds. Log: .tmp-preview-performance/checkout-purchase-exit-verified.log.
- After the final lock-order adjustment, **67 affected ingestion/native-delivery/purchase-exit tests passed**, 23.919 seconds. Log: .tmp-preview-performance/checkout-purchase-exit-lock-tests.log. Other runtime code was unchanged after the broad run.
- New coverage: multiple checkouts from one customer, exact versus unrelated token, later-created cart, purchase before first email, prior submitted/uncertain/accepted receipts, late and duplicate paid webhooks, missing token, unavailable checkout/customer/order details, repeated stop attempts, cancelled orders, no automatic reopening, submission boundary, zero attribution without accepted evidence and Sydney date/time.
- Existing coverage: normal exact recovery, manual enrollment/retry, native checkout scheduling, queue safety, analytics, Shopify event deduplication, consent/native unsubscribe, durable publication, pause/resume and lifecycle publication.
- Chromium production-table test passed at 1366, 390 and 320 px: date/time visible, purchase-stop label stable during ticking, no document overflow and no external network requests. Command: node tests/test_crm_checkout_purchase_exit_ui.cjs with the existing bundled Playwright dependency.
- During development, tests caught a missing shop column in the read projection and a NOT NULL deadline constraint; both fixed without schema changes. The batch-query counter also counted unrelated asynchronous thumbnail SQL, causing a cascade of leftover fixture requests. It now measures only its own request thread and retains the original constant-five-query assertion. Fresh database reruns passed.
- Optional local thumbnail prewarming still reports browser_runtime_unavailable; HTML/delivery/publication tests pass. No live provider submission, real customer preview or production write was performed.

## Specific production repair — proposed only

Read-only proof selection confirms journey 9083971b-407b-4912-ba0e-6f065a03f319 qualifies for the separate newer-purchase exit. After a separately approved deployment, the existing worker will stop it on its next eligible advancement; no Shopify checkout lookup is needed. For immediate correction, request separate approval to run the new stop_if_purchased helper **only for that journey** using the production store:

1. Reload and lock that journey; confirm it is ACTIVE, still belongs to the documented checkout/customer and is not itself recovered.
2. Recheck the signed payment proof and cancellation exclusions in the same operation.
3. Set STOPPED / NEWER_PAID_ORDER, clear retry_after, retain historical due time and block only unsubmitted PENDING/CLAIMED reminders.
4. Preserve the first checkout's recovery/order association, all submitted/accepted receipts, delivery history and the existing NO_MATCH attribution. Verify the table reads Purchased — reminders stopped.

Any broader repair must first enumerate other active journeys using the same proof predicate and review that candidate list. Do not blanket-cancel a customer's later carts, replay orders/webhooks, mark unrelated checkouts RECOVERED or increase conversions/revenue. No repair has been executed.

## Changed files and readiness

Runtime: crm_checkout_purchase_exit.py, crm_engine.py, crm_store.py, crm_automation_runtime.py, crm_shopify_automation_events.py, crm_webhooks.py.

Read/presentation: crm_checkout_analytics.py, crm_checkout_identity.py, crm_checkout_progress.py, crm_checkout_timing_ui.py.

Tests: tests/test_crm_checkout_purchase_exit.py, tests/test_crm_checkout_purchase_exit_ui.cjs, tests/test_crm_checkout_progress.py, tests/test_crm_checkout_enrollment_requests.py. One whitespace-only cleanup in tests/fixtures/crm_ultimate_preview.py resolved an existing task-wide Studio whitespace failure; no preview behavior changed. Documentation: this report. Studio static/infrastructure verification passed after that cleanup.

**Ready for local review and a separately authorized web/worker deployment.** Production repair, deployment and activation remain unperformed. The PGlite adapter verifies actual SQL/transactions but serializes fixture operations; independent multi-connection production concurrency was not exercised. Advisory lock ordering was reviewed and submission/ingestion guard regressions passed.
