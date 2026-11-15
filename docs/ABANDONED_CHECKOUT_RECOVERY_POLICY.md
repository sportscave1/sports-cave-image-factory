# Abandoned checkout recovery policy repair — 7 October 2026

## Status

Application repair implemented locally; not committed, pushed or deployed.
The requested all-country policy was saved and read back in the existing private
`crm_runtime_state` store. The currently deployed worker does not yet read it.
No recovery email, historical enrollment, Shopify mutation or send-record update
was performed during this task.

## Root cause and repair

Enrollment, manual enrollment and Engine.validate all called the same
subscription-only eligibility helper as promotional campaigns. The native
unsubscribe URL helper also rejected NOT_SUBSCRIBED profiles, even when Shopify
returned a usable unsubscribe URL. Checkout consent-update handling also stopped
recovery journeys solely on a newsletter-state change.

`crm_checkout_eligibility.recovery_eligibility` now owns the recovery decision;
`is_abandoned_checkout_recovery_eligible` exposes its boolean result. Newsletter
campaigns continue using their unchanged subscription-only helper.

Recovery checks verified recipient identity/email, both explicit opt-out sources,
local/provider suppression, incomplete checkout/recovery URL, complete line-item
pagination and returned variant/product availability. Queue owners retain active
flow/rule checks, delay scheduling, recovered-order evidence, immutable enrollment
identity, step receipts and provider idempotency. Send-time validation repeats
the dedicated policy. The validated native unsubscribe URL remains required.

## Configuration

Private key: `abandoned-checkout-policy`.

```json
{
  "version": 1,
  "regions": {
    "*": {
      "mode": "explicit_or_valid_inferred",
      "inferred_basis": "checkout_contact",
      "effective_at": "2026-10-07T10:07:33.391118+00:00"
    }
  }
}
```

The all-country override was explicitly requested by the owner. It means the
verified checkout contact is the configured recovery basis, not a newsletter
subscription. It is an application policy, not a finding about each country's law.
Explicit unsubscribe/redaction and suppression always veto recovery.
An ISO-country override takes precedence over `*`, e.g. `{"mode":"explicit_only"}`.
Country comes from shipping, then billing, then verified customer default address.
Without a configured override the default is explicit-only.

`configure_regions(store,user,regions)` uses existing automation-admin permission,
validates configuration and creates a new current-time cutoff when a rule changes;
it rejects caller-supplied backdated cutoffs. Reapplying the same rule preserves
its cutoff. No new settings page or per-page Shopify lookup was introduced.

`platform_eligible` fails closed because the actual Shopify AbandonedCheckout
schema supplies no independent recovery-permission boolean. The API also does
not certify shipping feasibility or expose a checkout risk decision; a recovery
URL is not presented as proof of either. No invented fields or legal-country
assumptions are used.

## Production audit / history safety

Read-only audit found 122 checkout ledger rows and one persisted
`consent_not_subscribed` / Marketing consent required evaluation.
The active flow had no region rules or recovery-consent policy.
The specific Shopify checkout was incomplete, AU, had a valid NOT_SUBSCRIBED
contact, a native unsubscribe link and an available ACTIVE Online Store product.

At the final count, exactly one existing displayed consent block changes under
the patched projection to Historical — not auto-enrolled. Zero of these blocked
rows were created after the new policy cutoff. This is not a claim that all
122 rows were newly evaluated or eligible.

Existing `checkout-auto-start-v2` and flow-activation cutoffs remain. Newly
permitted non-subscribers additionally must have a checkout created at/after the
policy cutoff. Existing receipts and idempotency keys are unchanged. No historical
batch was sent; no production send test was performed.

## Files

- crm_checkout_eligibility.py: central policy, boolean helper and admin configuration.
- crm_automation_runtime.py: enrollment and background reconciliation integration.
- crm_engine.py: delivery revalidation and newsletter-event separation.
- crm_automation_analytics.py: manual enrollment integration.
- crm_checkout_analytics.py: accurate cached reasons without per-row/network reads.
- crm_checkout_identity.py / crm_checkout_enrollment_requests.py: precise labels.
- crm_native_unsubscribe.py: independent recovery URL validation.
- crm_shopify.py: live product availability fields and bounded full pagination.
- Five checkout test modules: policy coverage, complete fixtures, changed labels.

## Verification

- 20 new policy/worker tests passed against disposable loopback PostgreSQL and
  mocked Shopify/provider. New non-subscriber checkout enrolled automatically,
  retained the configured due time, sent once through the existing worker and
  remained deduplicated. Delay wait, late opt-out, recovered checkout and historical
  exclusion were covered. No browser was involved.
- Focused 54-test run: 53 passed; one relative wall-time benchmark failed narrowly
  (2.655s against a 2.627s threshold). Isolated rerun of that benchmark plus all
  20 new tests passed (21/21); no assertion thresholds were weakened.
- Broader 104-test run exposed existing checkout timing/queue fixture failures.
  An unchanged HEAD-code baseline reproduced the historical timing, stale
  pagination/reconciliation, provider-queue, concurrency and manual due-time
  failures. They were not silently fixed or described as passing. Changed opt-out
  labels and newly required line-item fixtures were updated in tests.
- Python compilation and git diff --check passed.
- Updated Shopify query schema validation passed, with the existing deprecated
  Customer.email warning. Actual blocked checkout/profile read succeeded.
- Production policy readback and affected-row aggregate query succeeded.

Local test logs: `.tmp-checkout-new-tests.txt`, `.tmp-checkout-final-tests.txt`,
`.tmp-checkout-baseline.txt`, `.tmp-checkout-focused-final.txt`,
`.tmp-checkout-retest.txt` (ignored local evidence).

Live application behavior still requires deployment of the code repair. No live
email eligibility or delivery success is claimed from mocked tests.
