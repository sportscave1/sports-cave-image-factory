# Manual abandoned checkout recovery

The existing **Add to flow** action saves a durable request and the existing CRM
worker enrolls each eligible checkout and dispatches its first recovery email.
The first step is due immediately; the normal initial flow delay is bypassed.
The worker polls at its existing 2–5 second interval, and provider rate limits
still apply. Remaining steps retain their published delays after acceptance.

Historical classification only controls automatic enrollment. Explicit manual
requests may enroll historical checkouts, but must pass the existing approved
recovery permission policy, opt-out, suppression, customer identity, recovery,
purchase, flow rules, and re-entry checks. Those checks run again before sending.
Automatic enrollment retains its existing historical cutoff and timing.

The existing send ledger, leases, provider idempotency keys, sender configuration,
and frozen templates are reused. Cross-flow checkout send history is checked both
before enrollment and under the checkout lock at the submission boundary.
Accepted or uncertain submissions are never replayed by this action. Known
provider rejections can retry the same receipt and key after fresh validation;
uncertain outcomes remain held for reconciliation. Rate-limited sends remain
queued with the existing backoff.

The table displays Queued while pending and Sent only for a provider-accepted
receipt with a provider message ID. Each batch shows enrolled, sent, queued,
skipped, and failed counts, with skip reasons and safe provider error messages.
Polling updates the existing table without a second send action.

## Changed production files

- `crm_checkout_manual_dispatch.py`: targeted first-step dispatch and send history.
- `crm_checkout_enrollment_requests.py`: durable worker dispatch and outcomes.
- `crm_automation_analytics.py`: manual eligibility and fresh purchase checks.
- `crm_checkout_eligibility.py`: manual historical cutoff exception only.
- `crm_automation_runtime.py`: immediate first step and retryable failure handling.
- `crm_engine.py`: targeted claiming, fresh validation, safe provider errors.
- `crm_store.py`: targeted send lease and locked duplicate check.
- `crm_checkout_enrollment_ui.py`: asynchronous progress, counts, retry race fix.
- `crm_automation_analytics_ui.py`: immediate table status overlay.
- `crm_checkout_identity.py`: recovery status labels.
- `crm_checkout_timing_ui.py`: pending and failure timing labels.
- `components/crm_checkout_table/index.html`: existing pill styling for statuses.

## Validation and rollout

190 backend regression tests passed against the isolated local PostgreSQL-compatible
fixture, with mocked Shopify and email providers. Browser tests passed for single
and bulk actions, mixed outcomes, retry, automatic refresh, and four viewport sizes.
No real customer email was sent during testing.

No database migration, new dependency, new service, or Blueprint change is needed.
Deploy this application revision through the existing deployment process and
restart the existing CRM worker with the same revision. Preserve the canonical
`sports-cave-os` service as described in `RENDER_SERVICE_TOPOLOGY.md`.
This change has not been deployed by this implementation task.
