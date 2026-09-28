# Resend delivery — Stage 1

Local implementation only. No production configuration, commit, push, deployment,
provider send, Shopify data or subscriber state is changed by implementing this stage.

## Entry points

`crm_resend_marketing.py` owns configuration status, the single-recipient admin
diagnostic and a reserved, disabled production `send_marketing_email` function.
It uses requests, a fixed Resend URL, a 15-second timeout, no redirects and no
automatic retries. It does not import inbox providers, Shopify audiences or queues.

`crm_delivery_panel.py` renders under CRM & Marketing → Automations, above the
workflow-storage availability check. Only active admins see it; the service also
checks the active admin role, confirmation and one bare email address. The session
account follows the existing CRM Actions authorization pattern. There is no HTTP
test-send endpoint. The form accepts no customer ID, segment, list, template,
subject or body. Its recipient starts empty. Refresh/page load never sends.

## Configuration

The new service reads only:

- `RESEND_MARKETING_API_KEY`
- `RESEND_FROM_EMAIL`
- `RESEND_FROM_NAME`
- `RESEND_REPLY_TO`
- `CRM_MARKETING_ENABLED`

All four Resend fields are required. Keep `CRM_MARKETING_ENABLED=false`. The test
is deliberately available with that switch false; its fixed content states that
live marketing remains disabled. No secret is returned in configuration status.

The existing `crm_resend.Config` now uses these dedicated sender/key variables.
Its existing production and queued-template-test switches
(`CRM_MARKETING_SEND_ENABLED`, `CRM_MARKETING_TEST_ENABLED`) are additional locks,
both subordinate to `CRM_MARKETING_ENABLED`. They cannot bypass a false or absent
master switch. The old queued template-test feature is distinct from the new admin
diagnostic. Existing unsubscribe/public URL/webhook configuration is unchanged.
No flags are enabled or written by this implementation.

## One manual test, after approval

In an environment running this code with the above configuration, an active admin
opens Automations, types one test mailbox they control, checks the TEST ONLY
confirmation and clicks Send Test Email. Nothing is sent simply by opening the app.
This code is not yet available in the deployed app until separately approved.

The fixed message is from the configured name/address, has the configured Reply-To,
subject `Sports Cave OS — Resend Test`, simple branded HTML and a plain-text fallback.
Success means Resend accepted the submission, not confirmed inbox delivery.
The receipt is validated as a UUID before display. A UUID operation key is passed
as the Resend Idempotency-Key; do not manually repeat an uncertain submission.

Provider response bodies, exceptions and authorization headers are never echoed or
logged. Logs contain only fixed error categories and numeric HTTP status. Audit
writes use the existing `audit_logs` infrastructure, with action `resend_test_send`,
timestamp, recipient, sender, provider, operation ID, status, receipt ID and error
category. No message body or credentials are stored. Audit must accept a requested
event before the provider call; if unavailable, the send stops. Failure to save the
final receipt is reported separately and never causes a resend. This needs no CRM
workflow tables or new schema. Existing audit-table availability is still required.

## Stage 2 boundary

The result exposes a provider message ID and the request has a fixed test-purpose
tag. These can support later delivery-event correlation. No new webhook route,
subscription, suppression mechanism or event schema is introduced. The repository
already has `/webhooks/resend/crm`; this stage leaves it unchanged and does not
register it with Resend. Stage 2 must review that existing handler and suppression
storage before enabling any production delivery. The test bypass must never be
reused for campaigns or automation templates.

VentraIP support inbox, IMAP/SMTP, replies, Shopify consent and subscriber sync,
customer counts/search/filters and segment logic are unchanged.

API contract reference: https://resend.com/docs/api-reference/emails/send-email
