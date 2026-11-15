# One-recipient production-style Send test

Implemented locally, 29 September 2026. No delivery, consent mutation, commit,
push, deployment, or marketing configuration change was performed.

## Behavior

The existing top Send test popover, input, Enter/arrow submission, busy state,
success/error messages and admin permission remain intact. Only its existing
input help tooltip changes: “Send test uses the real Shopify unsubscribe link
for this customer.” Clicking that link in an actual delivered test will
unsubscribe that Shopify customer.

Previously CampaignStore rendered the default preview/test output without a
recipient URL, and the Stage 1 provider payload omitted List-Unsubscribe.

The test boundary now uses the existing Shopify.customers query with a quoted
email filter and fresh=True. It independently matches the normalized email to
one customer and that customer's default email, requires valid format and the
existing restrictive SUBSCRIBED consent decision, and checks the existing local
suppression store by customer ID and email hash. Incomplete/ambiguous lookup,
missing customer, consent, suppression, or URL failure blocks delivery.

Customer.defaultEmailAddress.marketingUnsubscribeUrl goes to the existing
render_campaign production path and the List-Unsubscribe header unchanged.
List-Unsubscribe-Post is omitted because Shopify POST one-click behavior has
not been verified. Preview continues using its harmless destination. No custom
unsubscribe secret is needed by this lookup; historical endpoints are untouched.

The subject retains [CAMPAIGN TEST], provider purpose remains campaign_test,
and the existing internal test receipt / TESTED draft status remain. No segment
is resolved; production queue, recipient totals, scheduling, and Send Now are
unchanged. Marketing ON/OFF does not control this manual test transport.

One fresh customer search is made per new valid test action. Accepted receipt
replay performs no customer lookup or second send. The existing transactional
idempotency guard, provider idempotency key, 60/hour admin transport limit and
15-second provider timeout remain. Catalogue tests use the saved content facts
without refreshing products or editions; production queue freshness checks are
unchanged. Catalogue test history redacts the native URL back to the placeholder
and records only a boolean indicating production unsubscribe use.

## Validation

- Connected Shopify read-only schema/field check and query: a subscribed
  customer returned a valid HTTPS native unsubscribe URL. No address, URL or
  token was printed; no link was clicked.
- Full CRM suite: 317 tests passed (53.914s).
- Final focused production-style test suite: 15 tests passed (0.256s), including
  a subsequently added real-adapter/mock-response freshness regression.
- Selected Email regression suites: 113 run, 112 passed, one existing skip
  (12.404s). Service, role parity, Sent lifecycle, Inbox selection, navigation,
  connection recovery, reconnect, send UX and signatures.
- Python compilation: all 13 changed/new Python files passed.
- git diff --check: passed.
- Streamlit AppTest coverage from the CRM suite passed; no separate browser
  screenshot run was needed for the tooltip-only UI diff.

All delivery tests used fabricated recipients, a disposable local SQL fixture
and a mocked provider. Tests cover exact one-recipient payload, production HTML
parity, matching List-Unsubscribe, no segment resolution/production queue,
receipt replay, consent changes after a prior lookup, missing and unsafe URLs,
local suppression, safe lookup errors, and token-free campaign history.

## Files

Runtime: crm_test_recipient.py, crm_campaign_store.py,
crm_resend_marketing.py, crm_campaign_send_ui.py.

Tests: crm_fixtures.py, test_crm_production_style_test.py,
test_crm_send_flow.py, test_crm_campaigns_v1.py,
test_crm_campaign_sections.py, test_crm_workspace.py,
test_crm_single_footer.py, test_crm_email_defaults.py,
test_crm_modular_catalogue.py (all under tests/).

No migration or new environment variable is required. The implementation reuses
the application's existing Shopify connection and API version. Schema references:
[customers email search](https://shopify.dev/docs/api/admin-graphql/latest/queries/customers)
and [CustomerEmailAddress](https://shopify.dev/docs/api/admin-graphql/latest/objects/CustomerEmailAddress).
