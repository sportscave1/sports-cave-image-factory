# Email recovery discounts V1 — local implementation report

Implemented locally on 9 October 2026. No commit, push, deployment, automation publication, Shopify discount mutation, checkout mutation, real order or customer email was performed.

## Editor and saved configuration

Each email in an abandoned-checkout automation has an optional **Recovery discount** setting: enable, search by code/name, select, inspect type/value/status, use, refresh, paginate, change or clear. Nothing is preselected for Email 3. Opening the control, searching and previewing do not change the saved document. A genuine selection stores Shopify identity, code, value wording and type in that email's `recovery_discount` document property. Existing draft persistence and immutable publication snapshots own this field; customer journeys continue using their frozen template versions.

The control is disabled for triggers that do not provide a verified original abandoned checkout. It does not invent a recovery destination for welcome or post-purchase emails. The existing editor, preview, transport and automation engine remain in use.

## Supported codes and accurate values

| Shopify code family | Display / personalisation |
|---|---|
| DiscountCodeBasic, percentage | Actual percentage, e.g. `15% off` |
| DiscountCodeBasic, fixed amount | Actual amount and currency, e.g. `A$5 off`; per-item qualifier where applicable |
| DiscountCodeFreeShipping | `Free shipping`; Shopify conditions remain authoritative |
| DiscountCodeBxgy | Shopify's actual offer summary |
| DiscountCodeApp | `App-calculated offer; value determined at checkout` because arbitrary Shopify Functions calculations are not exposed as a static amount |

Unknown or unverifiable types are not automatically applied. No approved-code list exists. Read-only live inspection confirmed **MYCAVE5 is an active fixed AUD 5 offer**, not 5%. It was not selected, changed or published by this work.

`{{discount_code}}` and `{{discount_value}}` work in subject, preview text and content. They are replaced on a render copy, with HTML escaping and header-control checks. Missing selections, unsafe URL interpolation and unresolved content block sending. The original authored tokens remain in published snapshots. Both variables are also available in the existing Personalise menu.

## Shopify API and permissions

Uses the existing authenticated `crm_shopify.Shopify` integration, read-only Admin GraphQL operations, its request throttling, 20-second request timeout and bounded transient retries. All six operations passed Shopify schema validation for **2026-01**. Required scopes are `read_discounts`, plus the existing `read_orders` and `read_customers` for checkout verification. A runtime `currentAppInstallation` check identifies missing discount access without changing permissions.

The connected Shopify MCP app has discount read access, and live search queries worked. This is **not proof that the separate Sports Cave OS app has that scope**. OS app credentials were unavailable locally; listing other app installations was denied. Verify that app's existing scopes before rollout; any scope change requires separate approval.

## Search, pagination and performance

No discount collection loads during ordinary page opening or preview refresh. Explicit searches run through a two-thread pool with four total in-flight/queued slots. Searches return at most 15 discount nodes and 20 codes per node, with separate cursors for discount and bulk-code pages. Exact-code lookup reaches codes outside a bulk group's first page. Display metadata has a 60-second, 64-entry, 2 MiB cache; delivery never trusts that cache. Refresh bypasses search-result caching. UI timeout is 30 seconds and retains editing access; pending background reads cannot send or modify anything.

Search completion uses a one-shot native composer-fragment event only while the open selector is waiting. It stops on completion, error, timeout or dismissal. This also supports the installed Streamlit runtime without keyed parent-fragment reruns. Search and preview work do not rerun the entire application.

Actual local measurements (fixtures, not production latency):

| Measurement | Result |
|---|---:|
| Open selector, headless Edge, 1440 × 950 | 272 ms |
| Search through selectable result, including simulated 600 ms API latency | 1,027 ms |
| Cold API search, three fixture reads at simulated 20 ms each | 61.343 ms |
| Same cached search | 0.024 ms; zero extra API calls |
| Existing warmed email render, best mean of 3 × 100 iterations | 0.838 ms |
| Render plus discount substitution and recovery-link application | 1.003 ms |
| Existing no-touch Email V4 editor, eight opens | 234–369 ms; saved revision stayed exactly 2 |

The feature adds approximately 0.165 ms to that local render fixture; it does not claim to accelerate Shopify itself. Benchmark reproduction: `python -m tests.email_discount_benchmark`. Browser fixture search adds intentional latency to verify asynchronous behavior.

## Original recovery link and combination safeguards

Shopify documents appending `discount=CODE` to the original abandoned-checkout recovery URL. The implementation reads that URL from the verified checkout, rechecks its Shopify ID, customer identity, completion state and exact URL immediately before sending, then appends a single encoded discount parameter. Existing query bytes, tracking parameters and fragment are retained. Product, variant and quantity data are not written or reconstructed. Only matching original-checkout links change; Wall Preview links stay unchanged.

Shopify explicitly warns that a recovery-link discount can replace a code manually entered during checkout. Therefore a different existing code, multiple discount parameters or a conflicting recorded checkout code **holds the email**, rather than overwriting the promotion. The same selected code is idempotent.

For standard automatic discounts, Shopify's documented best-eligible-discount rules remain authoritative. This does not promise that AUD 5 stacks with the existing 15% multi-buy promotion. Because product codes can displace automatic Buy X Get Y offers, that combination is held for review. Opaque automatic app discounts require reciprocal combination settings. More automatic offers than the bounded verification page can cover also cause a hold.

## Send validation and holds

Before provider submission, the worker reads current code facts, original checkout and active automatic-discount facts. It checks active dates/status, code identity, changed value/type, reported usage exhaustion, known subtotal/quantity minima and currency compatibility, known unavailable products, original customer/checkout identity and code conflicts. Deleted codes and unavailable/rate-limited Shopify verification produce actionable, sanitized reasons. No provider submission occurs for a discount hold.

Shopify still determines product/collection applicability, customer or segment eligibility, one-use-per-customer history, market restrictions, final usage races, stock availability at click time and app-calculated eligibility. The UI and preview explicitly say eligibility is checked at checkout; a URL never proves the discount was applied. Code status and inventory can change after an email is sent.

Holds use the existing `BLOCKED` receipt path and reason. They do not automatically retry, resend, rewrite a frozen journey or advance to provider submission. Existing retry controls do not reopen these blocked receipts. Correct the Shopify issue or review/reselect and publish for future journeys through the existing authorized workflow. Recovery of a previously blocked frozen journey requires an explicitly reviewed operational action; this feature does not silently change its offer or schedule.

## Preview and preservation

Preview shows the selected code/value and renders the discount tokens. A verified preview checkout gets the matching recovery CTA parameter; sample/invalid or conflicting contexts do not imply successful application. Preview uses the saved offer snapshot and cached checkout context, with no additional discount API lookup on refresh. Refresh/reselect in Settings retrieves updated offer metadata. Actual delivery always checks fresh facts and holds if the saved value/type changed.

Existing native checkout discovery, enrollment, purchase cancellation, consent, unsubscribe, suppression, provider idempotency, tracking, Wall Preview and immutable versions remain in their original paths. No webhook, schedule, checkout, theme, Edition Ops allocation or certificate behavior was changed. Internal test emails continue disabling recovery actions and use mocked transport in development tests.

## Verification

- Focused CRM regression suite: **267 tests in 31.631 seconds: 266 passed, one existing source-text assertion failed** (detailed below). Includes discount types, status/date/usage/minimum guards, markets, URL bytes/fragments, duplicate code conflicts, automatic promotion safeguards, paginated search, cache refresh, network/rate-limit failures, immutable snapshots, Email 3-only delivery, purchase cancellation, blocked sends, provider output and duplicate prevention.
- Edition regression suite: **84 passed in 5.922 seconds**, using disposable PGlite SQL. No allocation code changed.
- Browser suites passed: discount selector and saved SQL configuration; Personalise menu/cursor/undo/keyboard; publication save barrier; eight-cycle no-touch Email V4 editor. Both 1440-pixel desktop and 390-pixel overflow checks passed for the selector test.
- GraphQL: all six read-only operations valid against 2026-01; schema reports the three required scopes above.
- Python compilation and `git diff --check` passed.
- Known baseline failure: `tests.test_crm_automation_preview_stability.PreviewStabilityTests.test_automation_only_polling_and_debounce` expects a literal `not any(s['type']==BLOCK` in the unchanged `crm_section_ui.py`. That literal is absent in HEAD as well; neither that file nor the assertion was changed here. Other preview-stability tests pass, including the empty/failed-preview cases repaired during verification.

## Files and rollout

New application files: `crm_discount_api.py`, `crm_discount_ui.py`, `crm_recovery_discount.py`.

Integration changes: `crm_campaign_content.py`, `crm_campaign_page.py`, `crm_automation_definition.py`, `crm_automation_store.py`, `crm_automation_runtime.py`, `crm_automation_preview_cache.py`, `crm_abandoned_checkout.py`, `crm_abandoned_checkout_ui.py`, `crm_engine.py`, `crm_personalisation.py`, `components/crm_sections/personalise.js`. The last two extend the preceding uncommitted personalisation work.

Tests/fixtures: `tests/test_crm_discounts.py`, `tests/test_crm_discount_delivery.py`, `tests/test_crm_discount_ui.cjs`, `tests/fixtures/crm_automation_preview.py`, `tests/email_discount_benchmark.py`. Report: `docs/EMAIL_RECOVERY_DISCOUNTS_V1.md`.

No new migration, dependency, environment variable or service is required. A separately authorized deployment must include both the UI and existing email worker code. Confirm Sports Cave OS app scopes first. Then select the desired discount per email and use the existing review/publication workflow. Existing live automations remain unchanged until explicitly edited and published.

## Verified references

- [Shopify abandoned-checkout recovery discount links](https://help.shopify.com/en/manual/discounts/discounts-for-abandoned-checkout-recovery-emails)
- [Shopify combination rules and Buy X Get Y exception](https://help.shopify.com/en/manual/discounts/discount-combinations)
- [Admin GraphQL discountNodes, 2026-01](https://shopify.dev/docs/api/admin-graphql/2026-01/queries/discountNodes)
- [Admin GraphQL DiscountCodeNode](https://shopify.dev/docs/api/admin-graphql/2026-01/objects/DiscountCodeNode)
