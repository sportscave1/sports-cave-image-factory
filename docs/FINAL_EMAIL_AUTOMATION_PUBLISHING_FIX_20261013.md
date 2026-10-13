# Final email automation publishing fix — 13 October 2026

Implemented locally in task 20261011-54d8ff88. No commit, deployment, production mutation, real email or customer flow activation occurred. Prior unfinished preview work was preserved. This report supersedes the readiness requirements in AUTOMATION_PUBLICATION_LOCAL_REPORT.md.

## Causes and fixes

| Blocker | Proven code finding and correction |
| --- | --- |
| ORDERS_FULFILLED for payment-only Post Purchase | Readiness unconditionally required it. Now required only for enabled delivery-anchor or requires_fulfilment stages. ORDERS_PAID stays mandatory; Fulfilment Follow-up retains its fulfilment requirement. |
| Legacy unsubscribe endpoint/signing secret | Readiness called Config.unsubscribe_url, but outgoing mail already uses Shopify marketingUnsubscribeUrl from a fresh customer read. Removed that obsolete publication gate. Native HTTPS/address/consent validation, missing-link delivery block, footer and suppression checks remain. Legacy signer, endpoint, secrets and issued links remain untouched. |
| Stale heartbeat with newer schedule checkpoint | worker_health records only completion of an entire cycle, including slow analytics/maintenance. Live logs confirm cycles around five minutes plus approximately 39 seconds between cycles, exceeding the five-minute heartbeat limit. Added automation_delivery_health after completed dispatch/delivery work and renewed lease. It supplies genuine recent-work evidence without a timer heartbeat. Stale, failed or incompletely configured work remains blocking. Schedule evidence alone cannot authorize publication. Publication-consumer health is still required independently. |
| Wrong draft requirements | Default readiness preferred published_flow. Publish and Diagnostics now use the saved draft; Resume explicitly uses the published sequence. Worker/direct publication also recheck readiness inside the final transaction, preventing readiness lost during rendering from committing. |
| Resend validation | Truthy sender fields could pass. Lifecycle readiness and new worker health now validate single-mailbox sender/Reply-To, header safety and nonblank credentials. Existing supervisor already inherits the complete service environment into both children. No switches/credentials changed. Credential presence does not prove provider authentication/domain verification. |
| Checkout wording in lifecycle Diagnostics | Replaced irrelevant checkout messages with genuine delivery/full-cycle evidence and trigger-specific future-event information. Abandoned Checkout diagnostics retain their checkout messages. |

Existing confirmation, durable jobs, publication consumer, immutable versions, rollback/retry, revision/idempotency fences and draft/live separation were reused. Only enabled steps create active send steps and immutable email versions. Disabled editable content stays preserved. No HTML, templates, delays, preview controls, delivery recipient verification, consent, suppression, cancellation/refund checks or activation cutoffs changed. No webhook was registered or altered; no new infrastructure or migration was added.

## Tests

- **270 tests passed, zero failures/errors/skips, 26.678 seconds**, on fresh disposable PGlite PostgreSQL with actual repository migrations/SQL, synthetic Shopify/provider data and external transport blocked. Evidence: `.tmp-preview-performance/publishing-complete-tests-final.log`.
- **25 offline policy/cache/readiness tests passed**, 0.711 seconds. Evidence: `.tmp-preview-performance/publishing-offline.log`. Render topology and git diff whitespace checks passed.
- All five flows: durable request, worker processing, persisted publication, immutable history, pause/resume, draft changes, retries, rollback, repeated requests and no enrolment caused by publication.
- Payment-only Post Purchase: three preserved draft stages, Email 1 enabled at **10,800 seconds**, Emails 2/3 disabled. Actual local worker published exactly one active stage/version without fulfilled verification or legacy signer/base, and zero customer enrolments. Enabling a dependent follow-up blocks Publish Changes; Resume still checks the existing payment-only publication. Disabling dependent stages in a new draft is not blocked by an older published sequence.
- Actual DB lease/checkpoint persistence, failed-work health suppression, missing worker/scope/config blocks and loss of readiness after rendering before commit.
- Native recipient-specific unsubscribe rendering, unsafe/missing link blocks, consent/address binding and legacy compatibility; dynamic purchased/collection HTML; future-only lifecycle events, configured schedules and Abandoned Checkout regressions.
- Streamlit AppTest confirms zero jobs before explicit confirmation, Publishing before worker completion and Published only after persisted success. Existing editor/preview/collector regressions pass.

Initial broad run had five errors from a synthetic Welcome fixture claiming an available trigger but omitting its consent webhook. Corrected its evidence and reran all tests fresh; the safety check remains. Optional thumbnail prewarming reports browser_runtime_unavailable locally without blocking HTML publication/persistence. An attempted release smoke invocation required candidate/manifest arguments; release-candidate certification was not performed. The separate offline checks and topology validation above were completed.

## Production evidence and remaining checks

The user confirmed Nathan's Render workspace for read-only checks after the initial report. Inspected Render service metadata/deploys/logs and aggregate CRM health/capability records in the repository-documented authoritative Supabase project ceyzbfpuwuuxaiqwiltz. No customer records, rendered emails, secrets or configuration values were retrieved; no production writes occurred.

- Existing sports-cave-seo-worker (srv-d9ujm9navr4c73amurgg) is not suspended, has one instance and starts `python sports_cave_worker.py`. The supervisor started its CRM child after the successful deployment. Primary web and worker both run commit **1346de81362b1fdc8498f5a43ecac6a2fc6f1d03**; no deployed revision mismatch was found.
- CRM logs show repeated successful completed cycles. The five completions inspected between 16:50 and 17:15 AEDT on 13 October took 296.7, 299.2, 297.5, 299.9 and 305.6 seconds, plus approximately 39 seconds before the next cycle starts. This directly supports the stale full-cycle heartbeat explanation. No matching cycle-failure, publication-poll-failure or child-exit messages appeared in that filtered interval. Individual maintenance-operation durations are not logged sufficiently to attribute all elapsed time to a specific sub-operation.
- Persisted worker_health is `ok`, checked at **17:14:10 AEDT**, duration 304,360 ms, with marketing_enabled/provider_configured/sender_configured all true. The leased schedule checkpoint is newer at **17:15:55 AEDT**. The independent publication consumer is `ok` at **17:16:50 AEDT**. The new automation_delivery_health key is absent, as expected before this local fix is deployed.
- The configured-app diagnostic at **17:14:58 AEDT** verifies Shopify API/app identity, callback/HMAC, ORDERS_PAID and Abandoned Checkout topics. read_customers, read_orders, read_all_orders and read_products are present. Post Purchase, Win Back and Abandoned Checkout triggers are available. **CUSTOMERS_EMAIL_MARKETING_CONSENT_UPDATE and ORDERS_FULFILLED are genuinely missing**, leaving Welcome and Fulfilment unavailable. These gates must remain until separately authorized subscription registration/verification.
- Actual saved Post Purchase draft is unpublished: payment Email 1 enabled at **10,800 seconds**, requires_fulfilment false; delivery Email 2 and payment Email 3 disabled. The latter two retain their original delays and fulfilment guards. ORDERS_FULFILLED is therefore unnecessary for this draft's active sequence.
- Aggregate delivery history contains four production ACCEPTED receipts in the preceding 24 hours. This is read-only evidence that existing delivery has operated, not a test send or independent verification of the currently configured Resend credential/domain. Worker configuration presence is verified through its persisted booleans; secret values, web/worker environment equality and Resend domain API status were not directly inspected.

**The deployed CRM child and publication consumer are functioning. No restart or operational repair was performed. The local heartbeat correction remains undeployed.**

Required remaining read-only checks:

1. After a separately approved release, verify the new completed-delivery health record and confirm readiness remains stable throughout long cycles. Preserve the current worker/service architecture and SEO responsibilities.
2. Investigate individual maintenance durations only if ongoing delivery checkpoints become stale; current logs do not show a stopped CRM child, failed persistence or a stale publication consumer.
3. Check configuration presence/consistency without displaying values: RESEND_MARKETING_API_KEY, RESEND_FROM_EMAIL/NAME, RESEND_REPLY_TO, CRM_MARKETING_ENABLED and CRM_MARKETING_SEND_ENABLED. Verify provider authentication and sender/domain read-only. Do not automatically enable delivery.
4. Welcome needs its missing consent-update subscription; Fulfilment and enabled fulfilment-dependent Post Purchase changes need ORDERS_FULFILLED. The existing scripts/register_crm_webhooks.py registration mechanism checks installed app identity/scopes and avoids duplicating existing topics. Registration is a production mutation requiring separate approval; it was not executed. No registration is needed for payment-only Post Purchase. Refresh Diagnostics after any approved registration.
5. After a separately approved web and existing-worker release together, verify fresh worker evidence and rerun Diagnostics before explicit publication confirmation. Per-recipient native links and delivery safety remain mandatory.

Welcome, Post Purchase, Win Back and Fulfilment can use the existing framework once genuine requirements are satisfied. Abandoned Checkout publication, trigger, schedule, recipient verification and delivery decisions remain unchanged; the shared engine addition only records completed-work health.

**Ready for local code review; production deployment/activation readiness remains conditional on live checks and separate approval.**

## Changed files for this fix

Runtime/UI: crm_automation_readiness.py, crm_automation_publication.py, crm_automation_store.py, crm_automation_toolbar.py, crm_automation_diagnostic_ui.py, crm_email_diagnostics.py, crm_engine.py.

Tests: tests/crm_publication_fixture.py, tests/test_crm_lifecycle_publication.py, tests/test_crm_lifecycle_expansion.py, tests/test_crm_publication_readiness.py. Documentation: this report. Earlier preview changes remain separately documented in EMAIL_PREVIEW_ULTIMATE_PERFORMANCE_20261013.md.
