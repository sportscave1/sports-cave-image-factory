# Campaign sending permissions — local change

The deployed screenshot's aggregate administrator-verification warning is not a
literal string in this checkout. The corresponding backend manual gates were
`crm_campaign_send.ATTESTATIONS`: `CRM_DMARC_VERIFIED`,
`CRM_RESEND_WEBHOOKS_VERIFIED`, `CRM_MARKET_REVIEW_VERIFIED`, and
`CRM_BROADCAST_VERIFIED`. Preflight also required `postal_verified`,
`identity_confirmed`, and `domain_verified` (environment defaults include
`CRM_BUSINESS_ADDRESS_VERIFIED` and `CRM_SENDING_DOMAIN_VERIFIED`). These were
human attestations, not successful live provider checks.

Campaign production readiness now ignores those manual attestations. Actual
postal/contact configuration, sender/reply-to/API configuration, content checks,
unsubscribe links, tracking validation, current Shopify consent, suppressions,
exclusions, deduplication, immutable snapshot, optimistic version checks and
idempotent queue/worker behavior remain. Legacy settings are retained for
backward compatibility and other workflows; no schema migration is needed.

An active account with the existing `crm_campaigns_manage` permission can save,
send a campaign test, queue Send now or schedule. Existing page permissions were
not changed. Campaign test admin checks were removed from UI, send boundary,
store boundary and the campaign branch of the shared single-recipient transport.
The separate settings/admin diagnostic still requires an administrator.

Controlled tests still require one valid eligible Shopify test recipient and
confirmation, keep their audit/idempotency/rate limit, and never build a bulk
queue or mark the campaign SENT. They work with marketing OFF. Production still
requires `CRM_MARKETING_ENABLED=true`; the existing shared transport switch
`CRM_MARKETING_SEND_ENABLED=true` also remains unchanged. That operational switch
controls the shared worker, not per-user/manual approval. No environment values
were changed and no provider failure is bypassed.

The modal now shows `Production delivery ready` only after successful checks, or
`Production delivery issue: <specific blockers>`. No manual administrator warning
is rendered. The preceding fragment/instant-review work remains intact.

Files changed for this task:

- `crm_campaign_send.py`: remove manual readiness and test-role gates.
- `crm_campaign_send_ui.py`: Campaigns access for Send test; technical readiness wording.
- `crm_campaign_store.py`: remove redundant campaign-test administrator check.
- `crm_resend_marketing.py`: campaign tests require Campaigns permission; diagnostic unchanged.
- `crm_campaign_page.py`: legacy campaign test controls follow the same permission.
- `tests/test_crm_send_flow.py`: non-admin tests/queue/schedule, no-access denial,
  missing snapshot/master flag, real configuration failures, UI worker coverage.
- `tests/test_crm_review_modal.py`: ready wording and no administrator warning.
- This report.

Validation: 412 CRM tests completed successfully (one skipped) against disposable
local PostgreSQL and mocked transports. After the final UI assertions, all 28
focused send/review tests passed again. JavaScript modal regression, changed
Python compilation and diff whitespace checks passed. Existing suite exercises
consent/suppression, snapshot/version checks, duplicate sends and scheduling.
No live email, campaign or production record was changed. No commit/push/deploy.

Nathan can use the controlled test path after this local code is adopted, provided
the existing Resend configuration and test-recipient checks pass. Live delivery
was not exercised or certified by this task.
