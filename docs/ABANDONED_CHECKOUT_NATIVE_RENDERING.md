# Abandoned checkout: local implementation and validation

## Root cause and repair

The shared HTML editor is a conservative HTML renderer, not a Liquid runtime.
Pasted Liquid was displayed literally and could not supply trustworthy cart URLs,
images or prices. The enrollment already persisted `trigger_shopify_id` and the
worker already freshly checked that checkout/customer before delivery. However,
native frozen automation documents did not consume that context when rendering.
Campaign-only Auto Fill also appeared in the shared automation editor.

The native `abandoned_checkout_products` section carries only its type, section ID
and visibility. Cart facts are resolved into a render copy before sanitization,
validation and final rendering. Preview/customer data is never saved into the
draft or published template. No schema change or migration is needed.

## Three separate contexts

| Operation | Authoritative context | Recovery action |
| --- | --- | --- |
| Editor / Live Preview | Newest valid incomplete Shopify checkout | Actual checkout URL |
| Send Test | Fresh latest valid checkout, independent of test recipient | Disabled; no recovery URL in generated block |
| Published delivery | Fresh enrollment-bound checkout ID and matching customer | Only that checkout's recovery URL |

Live dispatch never queries the preview list. Existing consent, eligibility,
recovery, suppression, unsubscribe, tracking, publication-version and transport
idempotency checks remain in place. Final rendered size still passes the 95 KB
guard at dispatch. The existing recovery/signed-link exclusion keeps recovery
URLs unchanged by marketing tracking decoration.

Publishing validates the static authored content and retains the typed dynamic
block. Complete recipient HTML is independently validated at delivery. Raw Liquid
is rejected with guidance to use the built-in template; saved legacy content is
not silently rewritten. Apply **Abandoned Checkout — Collector Reminder** from
Templates in a Checkout abandoned flow, or insert the native products section.
Intro/outro HTML remains editable, and the standard global header/footer is reused.

## Preview performance and presentation

- Separate descending preview query: five candidates per page, at most four pages.
  Invalid/recovered/empty candidates are skipped. Unavailable provider reads are
  not reported as fictitious checkout data.
- Session cache is scoped by Shopify namespace and lasts 45 seconds. Initial
  reads use the existing bounded executor and shared Shopify throttling. In-flight
  refresh clicks reuse the existing request. No first-paint network wait.
- Dynamic preview fragments check completion every three seconds. This does not
  generate a Shopify call every three seconds; resolved data is reused until TTL.
- Line items use bounded, cursor-checked pagination, capped at 500. Incomplete,
  repeated or unstable pagination fails closed.
- Line totals use actual `discountedTotalPriceWithCodeDiscount.presentmentMoney`.
  Currency is displayed explicitly (AUD/USD), without conversion or invented price.
- Missing image/variant is supported. Real images remain uncropped, proportional,
  responsive and have escaped title ALT text. Existing Shopify WebP-to-PNG handling
  is reused. No image download occurs server-side.
- Live Preview sits between Save draft and Send test, uses cached production HTML,
  and has a bounded 480px canvas with existing Desktop/Mobile controls.
- Compact spacing and viewport-based editor iframe height apply only inside the
  automation editor. Campaign Auto Fill remains available in Campaigns.
- No fake checkout content, trust row, scarcity claim or customer mirror.

## Files changed

Runtime/UI: `crm_abandoned_checkout.py`, `crm_abandoned_checkout_ui.py`,
`crm_automation_runtime.py`, `crm_automation_store.py`, `crm_automation_ui.py`,
`crm_campaign_page.py`, `crm_campaign_send.py`, `crm_campaign_send_ui.py`,
`crm_campaign_store.py`, `crm_email_size_ui.py`, `crm_engine.py`,
`crm_html_workspace.py`, `crm_middle_sections.py`, `crm_section_ui.py`,
`crm_shopify.py`, `components/crm_sections/composer.js`.

Tests: `tests/test_crm_abandoned_checkout.py`,
`tests/test_crm_abandoned_checkout_ui.cjs`, `tests/test_crm_native_automations.py`,
`tests/fixtures/crm_automation_preview.py`,
`tests/fixtures/checkout_email_generated.html`,
`tests/fixtures/checkout_product_generated.png`.

Responsive screenshots are under `docs/performance-evidence/checkout-*` and contain
synthetic fixture data only. The browser test regenerates HTML from the current
renderer and supplies a local synthetic PNG; no external asset requests are made.

## Local evidence

- 160 Python regressions passed using disposable loopback PostgreSQL, mocked
  Shopify/Resend and external-request guards. This includes 17 focused checkout
  tests and real persistence/worker tests for published recipient isolation,
  recovered-checkout exit and idempotent manual tests.
- Browser: native template application, no automation Auto Fill, native section,
  Live Preview production output, working recovery link, no fragment exception.
- Editor widths: 1920, 1440, 1366, 1024, 768, 430, 390, 320px.
- Final-email widths: 600, 430, 390, 375, 360, 320px; no horizontal overflow,
  loaded image aspect ratio preserved, products and recovery CTA visible.
- Existing automation-home/editor browser regressions, section component and
  undo/redo tests passed.
- Python compilation, JavaScript syntax checks and `git diff --check` passed.

## Live limitations

All three checkout queries passed Shopify Admin schema validation (2026-04).
A bounded read-only query against the connected store returned five real recent
unrecovered checkouts. The newest had a customer, product, variant, image, quantity,
recovery URL and USD presentment price. No raw payload, customer identity or recovery
token was saved in this report or test fixtures.

The deployed OS editor was not changed or tested with this local build. End-to-end
live sending and specific customer's preview acceptance remain deployment checks.
No email was sent; no production records, Shopify data, configuration or deployment
were changed. No commit or push was made. Ready for a controlled deployment and
post-deployment preview smoke test; this is not a claim of universal email-client
rendering or production delivery verification.
