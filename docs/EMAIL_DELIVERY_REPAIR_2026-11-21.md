# Email delivery repair — 21 November 2026

Task: 20261120-1a17206e
Owner: codex-email-recovery-01a1fad3-20261121

## Confirmed production observations

- Black Friday campaign: 2,445 / 2,445 submitted to Resend, zero failed, skipped or held. Submission is not inbox delivery.
- A CRM cycle took 1,168,753 ms. Full-cycle worker health therefore appeared stale while the worker continued processing.
- Checkout trigger evidence expires after 10 minutes but was refreshed only at the beginning of a full cycle. Long cycles can outlive this evidence.
- Abandoned-checkout diagnostics explicitly excluded the existing completed-delivery checkpoint from their recent-work display.

## Focused code repair

- Refresh actual Shopify trigger evidence at delivery checkpoints, before native send validation, and before source reconciliation. Failed checks continue to fail closed; timestamps are never extended without verification.
- Yield after 45 seconds of due-checkout processing so queued delivery can run before another slow batch. A single in-flight provider read remains bounded by its existing timeout.
- Use completed delivery work for the abandoned-checkout health display and activity view. Recent lease activity alone cannot mark delivery healthy.
- Retain purchase exits, permission checks, availability checks, send identity and uncertain-submission protections.
- Live follow-up identified a second pre-submission failure: the edition label compared a nullable remaining count to zero. Render the verified edition limit when availability is unknown; never invent a next-available claim. The regression renders the complete recovery email with a null remaining count.
- Unexpected failures now retain code filenames, line numbers and function names only, excluding exception text, source lines, local values and recovery URLs.

## Branding already applied through the OS

Shared Header version 7 uses a transparent PNG with a subtle light keyline. The source logo shape and colours remain intact.
https://cdn.shopify.com/s/files/1/0722/2332/6515/files/sports-cave-email-logo-transparent-theme-safe.png?v=1795212144
The existing shared-branding policy applies this header to future campaign and automation submissions. Already-submitted emails are immutable.

## Validation

- python -m unittest tests.test_crm_delivery_freshness — 7 passed (fake clocks, Shopify and storage; no live sending).
- python -m unittest tests.test_crm_delivery_freshness tests.test_crm_automation_diagnostics tests.test_crm_shared_branding — 23 tests, 1 disposable-SQL test skipped after the added seventh regression.
- python -m unittest tests.test_crm_recovery_elements tests.test_crm_batch_dispatch tests.test_crm_checkout_eligibility tests.test_crm_shopify_automation_triggers tests.test_crm_checkout_purchase_exit tests.test_crm_discount_delivery — 104 tests, 54 requiring disposable SQL skipped.
- git diff --check; python scripts/validate_render_topology.py; Studio Verify passed.
- Full delivered-inbox and disposable-SQL integration checks have not been run. No production credential was used in local tests.
- Combined follow-up run with safe error-location and nullable-edition regressions: 129 tests, 74 passed and 55 disposable-SQL tests skipped. The recovery renderer retains the original recovery URL and avoids unsupported availability claims.

The user explicitly authorized committing, integrating into main, pushing and deploying this fix on 21 November 2026. The existing canonical OS and supporting worker are the release targets; no new service or Blueprint change is required. Production verification must follow the actual Render deployment.
