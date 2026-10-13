# Smart Catalogue and email size restoration — 13 October 2026

Implemented locally in task `20261011-54d8ff88`. No commit, deployment, publication, customer enrolment, production mutation or real email send was performed.

## Root causes and fixes

- Catalogue authoring previously stored only manual products. Added an optional `settings.smart` flag, defaulting existing blocks to Manual. The existing picker, layout, display options and CTA remain in use. Manual selection now survives the Smart round trip and reopening without losing its saved product choices.
- Smart rendering requires recipient facts rather than a shared template selection. The new adapter resolves a temporary recipient document; campaign preparation freezes each recipient's actual message in the existing dispatch snapshot. Retries use that snapshot and the existing idempotency key. Drafts, templates and published authoring documents retain the Smart binding rather than customer-specific products.
- Customer switching could reuse a visual editor model calculated for another recipient. The local preview key now includes the selected Smart customer and facts revision. Background completion cannot replace the current customer's preview with another customer's products.
- The original flow size indicator was moved into a tooltip by the compact-preview rollout in Git commit `a76a9109`. Restored the existing meter in the editor action area using `crm_email_size_ui`; no second meter implementation was added. Production HTML measurements are reused by the canvas and action row. Editing marks the meter as updating until the new measurement arrives; invalid content shows an unknown measurement rather than stale green status.

## Smart behaviour

- Shopify Storefront `productRecommendations` uses `RELATED` intent and the recipient's country context. Recent purchase products seed recommendations, while all locally recorded purchases contribute exclusions. A checkout contributes only when its Shopify customer identity matches.
- Lightweight sport, team and athlete title matching ranks relevant candidates. The established Shopify collection and catalogue adapters provide bounded fallback candidates. No paid AI, new database or service was added.
- Up to three eligible products are rendered with the existing catalogue HTML renderer. Owned, duplicate, unavailable, unpublished and sold-out editions are excluded. Missing required product/image/price/edition facts omit unsafe cards.
- Country-specific Storefront pricing supports recipients outside the editor's named markets. Unknown-country Global recipients get no invented Australian gallery. Missing regional facts fail closed.
- Existing viewed-product telemetry has no verified Shopify customer association. It is deliberately not used for customer recommendations; no browsing history or privacy permission is inferred.
- Storefront requests have short timeouts and bounded product-only caching. Visual facts are session/customer scoped and expire after two minutes. Campaign cold preview work uses the existing background pool. Product reads are shared within the existing 50-recipient preparation batch; customer consent and delivery verification remain uncached and authoritative.
- Smart mode persists through existing autosave, reopening, duplication, template storage and immutable publication. Manual mode remains the default. Smart never substitutes its products into a shared saved template.

Storefront queries were validated against Shopify's schema (artifact revision 3). [Shopify Storefront product documentation](https://shopify.dev/docs/storefronts/headless/building-with-the-storefront-api/products-collections/getting-started).

## Email size

The original green bar is visible in Campaigns and Abandoned Checkout, Welcome, Post Purchase, Win Back and Fulfilment editors. It uses the existing 80 KB safe threshold, 95 KB send limit and approximately 102 KB Gmail clipping reference. Yellow/red states and detailed tooltip remain. Measurement includes generated production HTML and existing URL allowance; remotely hosted image bytes are excluded. The compact 40 px preview toolbar remains unchanged.

## Verification

- **314 Python regression tests passed**, zero failures or skips, in **39.705 seconds** on the final application code. Coverage includes real disposable PostgreSQL SQL paths, campaign preparation, immutable publication worker processing, future-only enrolment, consent/unsubscribe, checkout recovery, personalised rendering, size validation and dispatch retry/accepted-receipt idempotency.
- Chrome/Streamlit Campaign editor checks passed at **1440 px and 390 px**: manual picker, distinct Alice/Bob recommendations, recipient switching, autosave/reopen, restoration of manual products, desktop/mobile, 80/96 KB warning transitions and safe catalogue fallback during a simulated Storefront failure.
- All five flow editors were exercised at both widths, with normal and Smart catalogue fixtures: visible size meter, personalised product bindings, HTML edit measurement updates and desktop/mobile switching.
- Final flow browser reruns exposed two fixture defects: a fixed 800 ms assertion sampled the loading shell, and a repeated mock wrapper could recursively call itself. The test now waits for actual artwork content and installs its mock adapter once per fixture session. These were test fixture defects, not claimed instantaneous production results.
- `git diff --check` passed. Shopify GraphQL schema validation passed.
- Fixtures used fabricated customers, orders and provider responses with a disposable loopback PostgreSQL engine. Browser traffic was restricted to loopback. These are actual editor/database integration checks, not live Shopify authentication or production performance measurements. No email was sent.

## Configuration and remaining limits

Ready for local review. Before an approved production deployment, verify Storefront product-channel access and the existing optional `SHOPIFY_STOREFRONT_ACCESS_TOKEN` or `SHOPIFY_STOREFRONT_PRIVATE_TOKEN` configuration. Admin credentials are never reused as Storefront tokens. API failures use verified existing catalogue facts when available; otherwise the gallery is omitted. Live market availability, real Shopify response latency and delivery must still be checked in an authorised production verification.

The Windows PowerShell Studio verification command timed out without output. Test results are recorded here; a successful new Studio metadata update is not claimed.

## Changed files

Recommendation adapter and rendering:
`crm_smart_catalogue.py`, `crm_catalogue.py`, `crm_middle_sections.py`, `crm_lifecycle_products.py`, `crm_section_ui.py`, `components/crm_sections/composer.js`, `components/crm_sections/preview.js`.

Recipient preparation, delivery and test rendering:
`crm_campaign_send.py`, `crm_campaign_dispatch.py`, `crm_campaign_store.py`, `crm_campaign_issues.py`, `crm_engine.py`, `crm_automation_runtime.py`.

Editor previews and original size indicator:
`crm_email_size_ui.py`, `crm_campaign_page.py`, `crm_local_preview.py`, `crm_html_workspace.py`, `crm_automation_toolbar.py`, `crm_flow_preview.py`, `crm_automation_preview_cache.py`, `crm_abandoned_checkout_ui.py`.

Regression coverage:
`tests/test_crm_smart_catalogue.py`, `tests/test_crm_smart_catalogue_ui.cjs`, `tests/test_crm_flow_size_ui.cjs`, `tests/fixtures/crm_smart_catalogue_ui.py`, `tests/fixtures/crm_flow_size_ui.py`, `tests/test_crm_email_size.py`, `tests/test_crm_template_picker.py`.

This report: `docs/SMART_CATALOGUE_EMAIL_SIZE_20261013.md`.
