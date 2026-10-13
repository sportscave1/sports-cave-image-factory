# Automation publication — local implementation

Date: 2026-10-13. Task: 20261011-54d8ff88. No commit, deployment, production activation or real email submission.

## Findings and changes

The existing durable publication queue, worker leases, transactional immutable versions, publication status reporting and event-anchored lifecycle delivery were already implemented. Independent release locks prevented expanded Welcome, Post Purchase and Win Back journeys from publishing, entering, advancing and resuming. Fulfilment already used native publication.

Removed the permanent `DRAFT_ONLY` switch, definition-level release lock, hidden toolbar action, inline action restriction, publication rejection, resume rejection and draft-only page message. Unpublished lifecycle definitions remain unable to deliver. Lifecycle timing contracts and Post Purchase fulfilment guards remain mandatory.

All five supported flows now use the existing publication lifecycle. Lifecycle Publish opens a confirmation naming the flow and explaining future delivery and no historical backfill. Content is checked before confirmation; the durable worker repeats authoritative checks. The UI remains Publishing until the persisted worker result succeeds. Publishing paused flows preserves their pause. Draft edits retain separate immutable published versions. Abandoned Checkout retains its existing publication, trigger, preview, test-send and delivery paths.

New lifecycle readiness checks require fresh Shopify diagnostics, relevant customer/order/product permissions, complete history access for expanded journeys and Win Back, required payment/fulfilment subscriptions, a recent working delivery worker with delivery/provider/sender configuration, a recent publication consumer, delivery configuration and signed HTTPS unsubscribe support. The existing email validator additionally checks saved content, subjects, preheaders, HTML/bindings, footer, tracked size and provider settings. Optional pixel status is not a blocker. Diagnostics and the disabled Publish tooltip expose specific missing prerequisites. Resume checks the live version's prerequisites.

Actual dynamic Post Purchase publication initially failed because offline validation attempted production rendering before resolving artwork bindings. Authoring validation now resolves a detached sample copy through the existing collector renderer. Immutable versions retain the original editable bindings; actual delivery still requires verified recipient facts and validates the final rendered size. No sample artwork is saved or dispatched.

Fixed Win Back reconciliation to select candidates using the published inactivity policy, preventing unpublished draft edits from affecting live eligibility. Existing activation cutoffs, purchase exits, cancellation/refund/risk checks, consent, suppression, frequency controls, idempotency and accepted-send history are retained. No backfill action was added.

## Verification

- 210 affected Python tests passed, no failures or skips, against disposable PGlite PostgreSQL using real repository migrations and synthetic Shopify/provider fixtures. External HTTP transport was blocked. Final run: 25.190 seconds; local durable request acceptance: 11.3 ms.
- Actual durable database tests cover all five flows: request/worker/activation, multistep delays, duplicate requests, pause/resume, draft/live separation, immutable history, failed validation rollback and retry, both dynamic Post Purchase gallery bindings, scopes/worker/delivery failures and no enrollment caused by publication.
- Lifecycle runtime tests cover fresh history, historical event cutoffs, historical Win Back thresholds, published inactivity policy, paid-order supersession, consent/purchase exits, event-anchored timing, restart idempotency and frequency protections. Existing Abandoned Checkout and native unsubscribe regression suites passed.
- Native Streamlit AppTest exercised Publish, explicit confirmation, zero jobs before confirmation, pending status before worker completion, and persisted success after the real local publication worker processed the job.
- Updated offline release smoke: 20 tests passed with networking forbidden. Render topology validation and `git diff --check` passed.
- Evidence logs: `.tmp-preview-performance/publication-final.log`, `publication-ui.log`, `publication-smoke.log`.

## Limitations and deployment readiness

The local implementation is ready for code review. Production readiness is conditional on diagnostics in the separately authorized production environment; production credentials/customer records were not inspected. Actual Shopify permissions, webhook subscriptions, provider configuration and deployed worker health cannot be certified from local fixtures. The new publication consumer heartbeat requires the updated existing worker to run before lifecycle activation becomes available. No additional service or migration is needed beyond the existing lifecycle/publication migrations.

Optional thumbnail prewarming logged `browser_runtime_unavailable` in this local environment. This did not prevent publication, HTML rendering, persistence or test completion; production thumbnail runtime was not verified. No actual provider delivery or production Shopify webhook was exercised. A browser screenshot acceptance run was not performed for this publication change; native Streamlit confirmation behavior was tested.

## Changed files

Runtime/backend: `crm_lifecycle_runtime.py`, `crm_lifecycle_definition.py`, `crm_automation_publication.py`, `crm_automation_store.py`, `crm_automation_readiness.py`.

UI: `crm_automation_toolbar.py`, `crm_automation_publish_confirm.py`, `crm_automation_diagnostic_ui.py`, `crm_flow_inline.py`, `crm_flow_page.py`.

Checks/fixtures: `scripts/sports_cave_deploy_smoke.py`, `tests/crm_publication_fixture.py`, `tests/test_crm_lifecycle_publication.py`, `tests/test_crm_lifecycle_expansion.py`, `tests/test_crm_automation_publication.py`, `tests/test_crm_native_automations.py`, `tests/test_crm_collector_v2.py`, `tests/test_crm_collector_personalisation.py`, `tests/test_crm_flow_inline.py`, `tests/check_lifecycle_browser.py` and this report.
