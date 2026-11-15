# Email subject and preview personalisation V1

Implemented locally on 9 October 2026. No commit, push, deployment, live data modification, automation publication or customer email was performed for this task. All email submissions in tests used mocked providers. Existing published templates are not edited; variables take effect only when the user authors and publishes them.

## Authoring

The native Automation Subject and Preview text inputs each have a compact **+ Personalise** menu. It inserts the selected token at the remembered cursor/selection, retains surrounding text, and uses the browser's native editing transaction for undo/redo. Arrow keys, Enter and Escape are supported. Opening/closing the menu does not change authored values. Insertion uses no network request or Streamlit callback; the existing input blur/save and publication barrier remain authoritative. Input length limits are enforced before insertion.

The existing Email Preview now shows resolved subject and preview text above the email. It uses the selected, verified checkout when available; otherwise representative values are labelled **Sample Preview** (or the existing sample abandoned-checkout label). A refresh uses the existing explicit preview refresh control. Preview data is never used as production authority.

## Variables and sources

| Token | Source and policy |
|---|---|
| `{{first_name}}` | Fresh Shopify customer already verified by the native delivery validation. Preview uses the selected checkout's customer. |
| `{{product_name}}` | Title of the first line in Shopify's returned checkout/order line sequence; product title is a fallback when the line title is absent. No sorting, random selection or unrelated product lookup. |
| `{{short_product_name}}` | The same verified title with a terminal Wall Art, Collector's Wall Art or Limited Edition Wall Art suffix removed. Identity words, people, years, events and rivalries are retained. |
| `{{sport_category}}` | Exact Shopify product-ID match in the existing Sports Cave product mirror; product type, tags and collection titles pass through `sports_categories.infer_sport_category`. Marketing collections are ignored. Conflicting sports produce a generic fallback; a specific Motorsport discipline takes precedence over the broad Motorsport category. |
| `{{edition_number}}` | Fresh read-only Edition Ops product/run projection before purchase; exact order/customer/product/line allocation lookup after purchase. No session-state authority and no allocation writes. |

For multiple products, **the first returned line is always primary**, including when that line has no verified edition. The resolver never searches another line for a more convenient number. Multiple units/allocations that cannot be represented by one unambiguous allocation produce a fallback.

Conservative shortening deliberately keeps “Crash” in “Dick Johnson Crash – Bathurst 1980”, and “Nostalgic Tribute” in the Shane Warne title. Removing these words without authoritative short-name metadata risks changing the product's identity. There are no AI calls or new Shopify API calls for this feature.

## Edition safeguards and fallbacks

Before purchase, authored fields containing the edition token must use exactly:

`Next available edition: {{edition_number}}`

The editor's menu tooltip explains this, and saving/publication validates it. This intentionally constrained wording prevents a subject or preheader from claiming a reservation. Availability is a preparation-time snapshot, not a guarantee. Values format as `#078/150`, using the actual limit rather than assuming 100.

The resolver rejects missing/ambiguous mappings, blocked/inactive records, exhausted counters, sold-out/expired/superseded states and invalid limits. Post-purchase lookup requires an existing valid, identity-enforced allocation for the exact customer, order, product and line; voided/refunded/cancelled/superseded allocations are excluded. It never substitutes the product's next cursor for an allocation. No cursor, sold count, remaining count, reservation or historical allocation is modified.

Missing first-name greetings lose their leading token and comma, e.g. `{{first_name}}, see your edition` becomes `See your edition`. Invalid names, control characters, template syntax in customer values and overly long substitutions cannot enter a header. Other unavailable values use readable whole-field fallbacks:

- Subject: `See your selected artwork`
- Preview text: `Explore your chosen artwork and current availability.`
- Edition field: `Check current edition availability`

Only the five variables are accepted. Unsupported/malformed template expressions and authored control characters are rejected. Final personalised fields are at most 250 characters; overlong identities use a field fallback rather than being cut mid-name. HTML preview/preheader rendering escapes values through the existing renderer. Substitution is single-pass, so Shopify content cannot introduce another template instruction. Logs record only failure class, not customer data or values.

## Delivery and compatibility

`Engine.validate()` carries the already verified customer and order alongside the existing checkout context. The native automation renderer verifies recipient/source identity, substitutes into a copy of the frozen document and then calls the existing renderer. Preview and internal tests use the same substitution function. Only requested data is read at production rendering: first-name-only messages do not query product or Edition Ops tables; product names reuse checkout lines; category and edition lookup are independent, bounded reads.

Authored/saved/published documents remain unchanged by rendering. Existing plain subjects/preheaders pass through unchanged. Triggers, 10-minute/12-hour delays, consent, suppression, purchase exits, recovery links, body sections/images, attribution, unsubscribe, Resend transport and idempotency code are unchanged. Manual internal test receipts still retain their existing replay safeguards.

Post-purchase production supports actual allocation lookup. The editor does not add an order selector; post-purchase editor previews use explicitly labelled sample data. An actual post-purchase send uses its verified order, never the preview sample.

## Verification

- **224 focused tests passed**, 25.873 seconds: new personalisation tests plus native automation, publication, stability, timing, Shopify triggers, checkout rendering/eligibility/reliability, editor and send-flow suites. Includes real disposable PostgreSQL reads, customer/product isolation, immutable published documents, mocked checkout delivery and exact subject submitted to a mocked internal-test provider.
- **60 Edition Ops tests passed**, 5.749 seconds, including disposable SQL cursor/version tests and allocation-integrity regressions.
- **10 final resolver tests passed**, 0.399 seconds, after tightening the empty-greeting fallback.
- Browser checks passed at desktop 1440 px and mobile 390 px: cursor insertion, selection replacement, multiple variables, keyboard, undo/redo, resolved header preview and no horizontal overflow.
- Existing publication save-barrier browser suite passed: pending-input acknowledgment, duplicate clicks, timeout rejection and retry.
- Python compilation and `git diff --check` passed.

An earlier expanded run executed 286 tests: 255 passed, one failed, 30 Edition SQL tests skipped because that fixture was not enabled in that run. The Edition tests were subsequently run with their fixture enabled. The one failure is the existing static assertion `PreviewStabilityTests.test_automation_only_polling_and_debounce`, expecting `not any(s['type']==BLOCK` in unchanged `crm_section_ui.py`. That string is also absent in the committed baseline; neither this source file nor that assertion was modified.

## Local performance measurements

| Measurement | Result |
|---|---:|
| Menu selection through input update, headless Edge | 71–90 ms across three local runs |
| Existing warmed email render, 100 iterations × 3 (best mean) | 0.206 ms/email |
| Same render plus subject/preheader substitution | 0.285 ms/email |
| Substitution alone, 1,000 iterations × 3 (best mean) | 0.065 ms/email |

These are local fixture/microbenchmark measurements, not production latency claims. Menu insertion makes no network call. Preview facts are reused within the selected preview context and refreshed explicitly; production edition facts are always read again. The UI adds a small script and two compact menus, with no polling or dependencies added.

## Files and deployment requirements

New application files: `crm_personalisation.py`, `crm_personalisation_data.py`, `crm_personalisation_ui.py`, `components/crm_sections/personalise.js`.

Updated integrations: `crm_campaign_page.py`, `crm_abandoned_checkout.py`, `crm_abandoned_checkout_ui.py`, `crm_automation_store.py`, `crm_automation_definition.py`, `crm_automation_preview_cache.py`, `crm_automation_runtime.py`, `crm_engine.py`.

Tests: `tests/test_crm_personalisation.py`, `tests/test_crm_personalisation_ui.cjs`. Report: this file.

No schema migration, dependency, environment-variable, webhook or service-topology change is required. A separately approved deployment must include both the application and existing CRM worker runtime so authoring and delivery share the resolver. Existing subjects remain unchanged until the user explicitly edits/publishes them. Product mirror metadata may be unavailable or ambiguous; that produces a fallback. No production delivery or production performance test was performed.
