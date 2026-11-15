> Release reconciliation: included in the October 11 authorized consolidated release; see `releases/SPORTS_CAVE_OS_FULL_SYSTEM_UPDATE_2026-10-10.md`. Historical local-only statements below describe the original task. Lifecycle customer activation remains locked.

# Email automation expansion readiness report

The local implementation adds Welcome Series, Post Purchase and Win Back to the existing automation workspace. It supplies ten editable draft emails, Shopify-backed audience projections, event-based eligibility and timing, and shared delivery safeguards. The changes are ready for local review. Production deployment and activation have not been performed or authorized.

All three expanded flows are Draft. All ten messages are Draft, including the optional fourth Win Back email, which is disabled. A server-side release lock rejects publication, activation, enrollment and customer delivery for expanded flows. The existing explicit internal test path remains available. No real recipient was used in testing.

## Existing implementation and reuse

The source was inspected before editing. The baseline is the working checkout captured at the beginning of this task, including its pre-existing uncommitted work; it is not an assumed clean Git HEAD. The source hash manifest records that boundary.

| Area | Existing source of truth and reuse |
| --- | --- |
| Automation overview and navigation | `crm_automation_ui.py`, `crm_automation_home_data.py`, `crm_automation_toolbar.py`; the same selected-flow navigation and toolbar are retained. |
| Flow layout and sequence | `crm_flow_page.py`, `crm_flow_thumbnail.py`; the same sequence rows, thumbnail previews, stage controls, analytics and diagnostics are used. |
| Abandoned checkout list | `crm_automation_analytics_ui.py`, `crm_checkout_analytics.py`, `crm_shopify_checkouts`; the existing cached/paginated checkout query, reconciliation, selections and detail operations are unchanged. |
| Table appearance and behavior | `components/crm_checkout_table/index.html`; new optional labels and a no-polling option have exactly the original defaults. No table CSS was changed. |
| Search, dates, sorting, pagination | Existing checkout queries remain authoritative for Abandoned Cart. New flow audiences use one local SQL query per page, 50 visible records plus one next-page sentinel, existing asynchronous read helpers, and the same table. |
| Customer detail, timeline and history | Existing enrollment/send/delivery ledgers and `recipient_details`; the new audience drill-down adds verified Shopify identity, order facts and draft timing previews. |
| Composer and draft editing | `crm_campaign_page.py`, `crm_html_workspace.py`, `crm_section_ui.py`, `components/crm_sections/composer.js`; no second composer or editor framework. |
| Preview and internal test send | `crm_automation_preview_cache.py`, `crm_abandoned_checkout_ui.py`, `crm_campaign_send.py`, `crm_test_recipient.py`, `crm_flow_tests.py`; the existing renderer, internal-recipient authorization and separate test ledger are reused. |
| Draft persistence and revisions | `crm_automation_store.py`, `crm_automation_definition.py`, `crm_automations.config`; expanded drafts additionally snapshot revisions before changes. |
| Publication and live slot identity | `crm_automation_publication.py`, `crm_automation_live.py`, immutable template versions; publication is explicitly blocked for this draft release. |
| Scheduling and manual operations | `crm_automation_timing.py`, `crm_automation_runtime.py`, `crm_flow_page.py`; new flows use absolute event anchors while Abandoned Cart retains its existing timing path. |
| Event ingestion | `crm_webhooks.py`, `crm_shopify_automation_events.py`, signed webhook event IDs and `crm_webhook_events`; existing event ingestion remains intact. |
| Background processing | `crm_worker.py`; bounded audience reconciliation runs in its existing preparation thread. No additional Render service, worker process or scheduler is introduced. |
| Delivery and idempotency | `crm_engine.py`, `crm_store.py`, `crm_resend.py`, `crm_marketing_sends`; existing claims, leases, frozen content, provider integration and uncertain-send handling remain authoritative. |
| Consent and suppression | `crm_logic.py`, `crm_suppressions`, existing Shopify consent/unsubscribe and provider suppression checks; consent must be currently subscribed, never inferred from an order or checkout email. |
| Analytics and attribution | `crm_checkout_analytics.report`, automation home metrics, `crm_marketing_sends`, `crm_delivery_events`; new flow reporting uses these ledgers and their existing empty states. No fabricated metrics. |
| Audit | Existing event, enrollment, send, template and publication records plus additive draft-revision and staged-preview records. Conversion does not delete journey history. |
| Database contracts | Existing CRM migrations beginning with `20260927093818_crm_marketing_v1.sql`, native automation, Shopify trigger, publication, reporting and flow-test migrations; orders come from `20260625_stage1_supabase_operational_ledger.sql`. |
| Regression tests | Existing abandoned-checkout, timing, flow v4/v5, native automation, Shopify trigger, publication and live-stage suites; existing local PostgreSQL and browser fixtures. |

## Files changed

Existing modules changed for explicitly marked lifecycle flows:

- `crm_automation_definition.py`: validate event anchors and fulfilment policy.
- `crm_automation_store.py`: opt-in expanded creation, preserved legacy conversion, revision snapshots, and draft/fulfilment safeguards.
- `crm_automation_ui.py`: route new/legacy lifecycle drafts into the shared experience and show accurate re-entry/timing controls.
- `crm_automation_toolbar.py`: show draft activation lock.
- `crm_flow_page.py`: display absolute stage timing and the new audiences inside the existing layout.
- `crm_automation_publication.py`: publication guard and lifecycle metadata in frozen content.
- `crm_automation_runtime.py`: scoped lifecycle dispatch and paid-purchase exits.
- `crm_engine.py`: scoped eligibility and real-product hydration through the existing sender.
- `crm_store.py`: scoped recipient serialization and 24-hour promotional cap.
- `crm_worker.py`: bounded background display-cache refresh.
- `components/crm_checkout_table/index.html`: optional labels and polling configuration with unchanged checkout defaults.

New implementation files:

- `crm_lifecycle_definition.py`, `crm_lifecycle_policy.py`, `crm_lifecycle_runtime.py`.
- `crm_lifecycle_audience.py`, `crm_lifecycle_ui.py`, `crm_lifecycle_sync.py`.
- `crm_lifecycle_shopify.py`, `crm_lifecycle_products.py`.
- `migrations/20261010112655_crm_lifecycle_draft_expansion.sql`.
- `docs/lifecycle-order-facts.graphql`, `docs/lifecycle-product-availability.graphql`, `docs/lifecycle-expansion-rollback.sql`.

New verification files: `tests/test_crm_lifecycle_expansion.py`, `tests/lifecycle_baseline.py`, `tests/run_lifecycle_checks.py`, `tests/fixtures/crm_lifecycle_preview.py`, `tests/check_lifecycle_browser.py`, `tests/check_lifecycle_table_regression.py`, `tests/benchmark_lifecycle_audience.py`, `tests/lifecycle_review_evidence.py`. Review artifacts are under `docs/lifecycle-expansion-evidence/`. Unrelated pre-existing repository changes are outside this task's change list.

## Database migration and preservation

The additive migration creates `crm_lifecycle_customers`, `crm_lifecycle_staged` and `crm_lifecycle_revisions`, enables RLS, revokes public/anonymous/authenticated access and adds order/customer and webhook lookup indexes. Server database access remains through the existing repository connection. Applying the migration twice was tested successfully. It neither creates enrollments nor changes automation statuses or existing checkout records.

The existing `shopify_customers` cache is derived from orders and cannot establish subscriber consent. The new projection stores verified responses from the existing Shopify customer adapter; it is not a second Shopify client or an independent order ledger.

Preparing an existing Draft is explicit and idempotent. It preserves the automation ID, complete old configuration, revision number, source steps, template IDs and editable email snapshots, and then increments the revision. Existing audit and delivery tables are retained. The audience detail offers an explicit copy of preserved content into a selected shared-editor draft; this copy creates another audited revision. Missing legacy templates abort conversion without a partial write. Active flows cannot be converted.

Rollback should revert the application and leave additive tables intact. The supplied reviewed-one-ID rollback recipe preserves the expanded revision before restoring a prior Draft. It defaults to `ROLLBACK` and is not a blanket migration-down script. Do not drop populated audit tables. Existing deployments remain compatible with the additive schema.

## Shopify sources and freshness

- Subscribers: existing `Shopify.customers` pagination and `emailMarketingConsent.marketingState`, opt-in level and consent timestamp. Only `SUBSCRIBED` can qualify. Pending double opt-in is held. Source is shown as unavailable when Shopify does not provide it; no invented signup attribution.
- Orders and products purchased: existing `shopify_orders`, original Shopify GIDs and preserved raw line items from existing order synchronization. Full paid state is required; authorization and partial payment do not qualify.
- Payment timing: signed `orders/paid` timestamps. A historical paid order with no verified payment timestamp is held for Post Purchase. For historical inactivity display, verified-paid order creation time is the explicit fallback when its original payment event is unavailable.
- Fulfilment and delivery: existing signed fulfilment events plus a batched read-only extension of the same Shopify transport. Delivery requires actual delivery timestamps for all successful shipments of a fully fulfilled order. Fulfilment is never labeled as confirmed delivery.
- Risk, disputes and returns: the same batched order-facts query; unavailable live facts fail closed. Full refund/cancellation/payment state is rechecked from current orders. Inappropriate promotional messages are held.
- Lifetime spending: Shopify Customer `amountSpent`, with currency. Missing verified spending is displayed as unverified rather than substituting gross order totals.
- Recommendations: the existing local `shopify_products` index, bounded candidate selection, batch availability verification, and existing `Catalogue.resolve`/catalogue cards. Purchased items are excluded from automatic suggestions. Sport matching is preferred. The first Win Back email requires products created after the last purchase. No invented prices, scarcity, reviews or discount codes.

No page issues per-row Shopify requests. Customer synchronization is incremental with a cursor, a five-minute overlap and monotonic source timestamps. Older responses cannot restore superseded consent. Privacy redaction remains authoritative. Background batches are bounded to 50 customers and 20 enriched orders. Existing complete order synchronization is still required; this change does not start a duplicate full-order import.

## Draft emails and timing

All offsets are editable and measured from the named event, not from the previous email's actual send time. The review bundle contains ten complete Draft documents in `lifecycle-expansion-evidence/ten-email-drafts.json`. These definitions and fixture drafts were created locally; no production draft record was written.

| Flow | Internal name | Timing | Initial state |
| --- | --- | --- | --- |
| Welcome | Welcome to the Collector Vault | Immediately after confirmed subscription | Draft |
| Welcome | Find Your Sporting Legend | 3 days after confirmed subscription | Draft |
| Welcome | Own a Piece of Sporting History | 7 days after confirmed subscription | Draft |
| Post Purchase | Welcome to the Collection | 1 day after verified payment | Draft |
| Post Purchase | Display Your Sporting Legacy | 7 days after confirmed delivery; configurable fallback of 14 days after verified full fulfilment | Draft |
| Post Purchase | Build Your Collection | 45 days after verified payment, with successful fulfilment/delivery required | Draft |
| Win Back | See What's New | 90 days after latest qualifying purchase | Draft |
| Win Back | More Legends You'll Love | 105 days after latest qualifying purchase | Draft |
| Win Back | The Collector's Reminder | 120 days after latest qualifying purchase | Draft |
| Win Back | One Last Look | 150 days after latest qualifying purchase | Draft, disabled |

The fallback can be disabled or set to 14–90 days. Missing required events produce a hold. Editing timing cannot remove the built-in Post Purchase fulfilment guard. Copy uses the requested names, subjects and CTAs, existing responsive branding and shared content sections. The unverified 15% offer and optional incentive are omitted. Existing first-name/product/sport personalization and safe fallbacks are reused; order details and recommendations come from verified customer/order context. No separate template system was added.

## Eligibility and conflict handling

Welcome is once per customer/email identity and exits after a qualifying purchase. Post Purchase retains at most one active sequence per identity: the latest qualifying paid order deterministically supersedes the previous sequence, preserving previous receipts. Win Back uses the latest qualifying purchase, one sequence per order-based inactivity cycle, and a minimum 90-day re-entry cooldown; a new purchase stops the current cycle.

Before each queued marketing message, current customer consent, suppression, complete order history, flow/step membership, risk, relevant event deadlines and content are revalidated. Complete-history access requires verified `read_customers`, `read_orders` and `read_all_orders`; the new runtime refuses incomplete history. Recipient advisory locks serialize new-flow entry, paid exits and send reservation. Existing unique queue identities, lease tokens and immutable accepted/uncertain receipts protect retries. A 24-hour cap covers the three new promotional flow types and does not modify Abandoned Cart's sending policy.

Historical records are visible in audiences and timing previews. “Stage eligibility preview” writes only a revision-bound audit preview, never an enrollment or send. Historical thresholds before activation are not automatically replayed. This release intentionally has no control that can activate historical sending.

## Validation results

The final selected regression run passed **181 tests, zero failures, zero skips**, versus **153 passing existing tests** on the original source. Tests use deterministic clocks, fabricated customers, mocked Shopify/Resend and isolated loopback PGlite PostgreSQL fixtures. Expected blocked-send and injected-error logs are test cases, not production delivery attempts.

Coverage includes ten rendered drafts, consent/pending opt-in, payment states, latest-order selection, verified delivery versus fulfilment fallback, partial shipments, refunds/cancellations/risk, absolute timing, purchase exits, Win Back thresholds/cycle deduplication, worker restart, duplicate entry, frequency caps, draft/revision guards, real SQL audience filters/sorting/paging, repeatable migration, RLS privileges, shared previews, explicit test-only delivery, and the existing checkout/publication/live-stage regressions.

Browser checks exercise all four actual shared Flow/composer components, new audience search/detail, subject save/reload, draft-only toolbars, desktop and narrow layouts, including the shared composer at 390 pixels. They block external browser requests and replace outbound Python requests with a failing guard. The table regression compares the captured original HTML against current defaults: **zero differing pixels at 1440 and 620 pixels**, with identical detail-button events. Screenshot fixtures use prewarmed synthetic thumbnails to isolate page/composer behavior from browser installation and image-render subprocess startup.

Both new GraphQL documents passed Shopify Admin schema validation for API version 2026-04. See the official [Order](https://shopify.dev/docs/api/admin-graphql/2026-04/objects/Order), [Fulfillment](https://shopify.dev/docs/api/admin-graphql/2026-04/objects/Fulfillment) and [Product](https://shopify.dev/docs/api/admin-graphql/2026-04/objects/Product) contracts. Schema validation does not establish the installed production app's permissions.

The checkout-specific modules, renderer, composer, checkout queries, consent policy, Shopify client, tracking and provider modules were not edited. A manifest verifies 147 existing root CRM modules unchanged; the ten changed root modules have the explicit lifecycle branches listed above. No existing checkout data, timings, emails or live automation records were modified.

## Performance evidence

`browser.json` records individual before/after page, composer-preview, search and warm-return measurements. These are local Edge/Streamlit fixture timings, not production measurements. There are three page samples and one interaction sample per flow; small differences do not establish an improvement or a production regression. Initial application/database fixture setup is excluded from the final warm comparison. Browser search includes an explicit 500 ms harness wait and the shared one-shot asynchronous read refresh.

| Local browser surface | Median page ready | Editor shell | Preview ready | Warm return | Search |
| --- | --- | --- | --- | --- | --- |
| Original Abandoned Cart | 331.97 ms | 141.44 ms | 232.58 ms | 225.26 ms | Existing checkout tests |
| Abandoned Cart after expansion | 355.50 ms | 231.00 ms | 242.27 ms | 254.79 ms | Existing checkout tests |
| Welcome | 418.92 ms | 195.83 ms | 293.58 ms | 261.89 ms | 1,373.76 ms |
| Post Purchase | 355.66 ms | 260.08 ms | 268.16 ms | 281.21 ms | 1,379.23 ms |
| Win Back | 433.66 ms | 214.77 ms | 315.31 ms | 382.35 ms | 1,350.84 ms |

The separate 10,000-customer/10,000-order SQL benchmark uses six samples per query, discards the first, and records five warm samples. Final first-page/search medians after refreshing planner statistics were Welcome **36.06/34.88 ms**, Post Purchase **45.25/68.01 ms**, and Win Back **49.35/49.70 ms**. Each list uses one SQL call, returns at most 51 rows and makes zero Shopify calls. This is a bounded synthetic benchmark, not a production capacity guarantee.

The initial benchmark without statistics showed a 3,876 ms Post Purchase first-page median. Refreshing statistics corrected the plan; the application query did not need a separate implementation. Both measurements are retained. Run normal `ANALYZE` maintenance after the initial authorized bulk cache load and verify actual production query plans. No performance improvement is claimed for Abandoned Cart.

## Deployment and activation prerequisites

1. Review this task's changes separately from the repository's pre-existing dirty work. A future commit, push, deployment or production mutation requires fresh explicit authorization.
2. Apply the additive migration through the existing migration process and verify server access/RLS. Verify existing customer/order/product synchronization coverage, then allow bounded draft-only reconciliation to populate the projection. Refresh planner statistics after the initial bulk load.
3. Prepare each existing legacy Draft explicitly and inspect its preserved snapshots. Inspect real subscriber, paid-order and inactive-customer audiences before selecting any future enrollment cohort.
4. Confirm the installed Shopify app's complete-history/protected-customer-data access, read-only product/inventory and risk/dispute/fulfilment access, signed subscription and paid-order webhook health, and actual delivery evidence. Read-only schema checks cannot confirm these production capabilities.
5. Review real catalogue selections, collection/contact links, limited-edition and certificate wording, sender/footer/unsubscribe configuration, and any approved offer. Generic collection/contact CTAs are draft copy pending storefront review. Select real products in the existing picker for publication review; never insert invented examples into live content.
6. Activation requires a separately reviewed change removing the draft-release lock, explicit active publication, a controlled future cohort and an authorized internal-recipient test. No automatic historical stage replay should be enabled. Optional Win Back email 4 remains disabled unless explicitly enabled.
7. Before live activation, test independent-process contention on the deployment's PostgreSQL service and verify provider idempotency/uncertain-send behavior in an authorized staging environment. The local PGlite adapter serializes transactions and cannot prove networked multi-process lock contention, despite exercising duplicate threaded entry and the real SQL guards.
8. Render topology is untouched. If a later authorized release syncs a Blueprint, follow `docs/RENDER_SERVICE_TOPOLOGY.md`, run the topology validator and inspect the Blueprint preview. Never create another primary web service.

## Remaining limitations

Production data, installed Shopify scopes, historical sync completeness, live product availability and live delivery events were not inspected or altered. Existing customer/order IDs and draft content in production therefore still require the read-only deployment review described above. The runnable UI fixture contains fabricated records only; application audiences read real local Shopify projections and contain no demo-data fallback.

A customer history exceeding 1,000 orders is held for manual review. Missing historical payment timestamps cannot start Post Purchase timers; historical inactivity uses the documented verified-paid order-date fallback. Preview data can lag background reconciliation; actual future sending rechecks authority immediately before submission. Cross-sell recommendations prioritize a detected sport and availability, rather than promising an athlete-specific match when metadata is missing. Draft catalogue sections can remain empty until real selections are reviewed; the delivery adapter fails closed when required recommendations cannot be verified.

The legacy snapshot restore control, actual full Sports Cave OS shell with its authenticated account, networked PostgreSQL contention, real Shopify authorization, and production-sized deployment latency still need staging review. The local tests establish the shared-component behavior and database contracts; they do not certify those external conditions. No deployment, activation, commit, push or live email was performed.
