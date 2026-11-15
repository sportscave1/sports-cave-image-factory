# CRM & Marketing V1 — completion report

Implemented locally against fabricated Shopify/Resend data and disposable local PostgreSQL. Customer marketing and test delivery remain disabled by default. No production actions were taken.

1. **Files changed.** Existing integration files: `app.py`, `app_search.py`, `os_accounts.py`, `webhook_server.py`. New implementation: `crm_navigation.py`, `crm_page.py`, `crm_shopify.py`, `crm_cache.py`, `crm_audience.py`, `crm_logic.py`, `crm_store.py`, `crm_service.py`, `crm_engine.py`, `crm_worker.py`, `crm_templates.py`, `crm_resend.py`, `crm_webhooks.py`, `crm_http.py`. New migration: `migrations/20260927093818_crm_marketing_v1.sql`. Registration helper: `scripts/register_crm_webhooks.py`. Tests/fixtures: `tests/test_crm.py`, `tests/test_crm_boundaries.py`, `tests/test_crm_postgres.py`, `tests/test_crm_ui.py`, `tests/crm_fixtures.py`, `tests/crm_db_fixture.py`, `tests/crm_postgres_server.mjs`, `tests/fixtures/crm_preview.py`, `tests/fixtures/crm/package.json`, `tests/fixtures/crm/package-lock.json`, `tests/profile_crm.py`. Documentation: this report and `docs/CRM_MARKETING_V1_SHOPIFY_FIRST.md`.

2. **Navigation.** CRM & Marketing disclosure directly after Email; Customers, Segments, Automations, Campaigns, Templates, Reports. Existing route dispatcher, sidebar helpers and permission registry are reused. Top-bar search gains navigation entries only.

3. **Email untouched.** Git diff confirms no changes to support-email Python files, its component, SMTP, signatures, top-bar component or Files. All focused Email regression modules pass.

4. **Live architecture.** Existing Shopify authentication/GraphQL transport → paginated read-only CRM provider → bounded memory display cache → CRM UI. Private PostgreSQL stores workflow control state only. No Shopify customer mirroring job.

5. **Customers.** Live 50-row pages, search, consent/country/order/last-purchase/interest/segment filters. Aggregate counts come from Shopify. Filters applied to a fetched segment page are labelled. Lifetime Revenue remains `—` rather than initiating a full-store scan.

6. **Profiles.** Live identity, consent/timestamp, value, average order, first/last order, paginated orders/products/variants, on-demand interests and editions, native segment membership, marketing history and existing Email navigation. Interests/Segments cells defer detailed work to the profile instead of issuing calls per visible row.

7. **Caching.** Customers/orders/member counts 45s; native segments 90s; checkouts 20s; line pages 30s; products 180s; derived purchase facts 45s. LRU: 256 entries / approximately 12 MiB. Fresh-send reads bypass it. Audience count state is transient session memory, not membership storage.

8. **Throttling.** Two in-flight Shopify requests per process, cost/throttle and Retry-After awareness, at most three transient attempts, bounded waiting. Nested list requests are limited; checkout reconciliation omits contents, and detailed lines/collections paginate separately.

9. **Order/value data.** Native `amountSpent` and `numberOfOrders`, first/last orders and paginated live Shopify order relations. No CRM order or revenue table.

10. **Consent.** Only valid SUBSCRIBED customers can pass. Missing, invalid, redacted, pending, unsubscribed and not-subscribed are denied. Current consent/address are fetched before every delivery, followed by local and provider suppression checks. No Shopify consent writes.

11. **Shopify segments.** Live definitions, timestamps, native counts/member pages and batched customer resolution. Individual preview/count is deliberate; no N+1 count query for every segment on initial page load.

12. **Sports Cave definitions.** Seventeen seeded rule definitions, validated bounded AND/OR rules, editable VIP threshold. Complex purchase/interest/edition rules resolve current data on demand.

13. **No membership persistence.** No Shopify or custom customer-membership table exists. Only an executing campaign's minimal recipient receipts are durable.

14. **Interests.** Derived from live purchased products' types, tags and collection names; memoized in bounded memory. No customer-interest mirror.

15. **Edition Ops.** Read-only existing `edition_orders` lookup using customer ID/exact email. No ownership allocation, copies or edits.

16. **Abandonment.** Checkout events expedite authoritative `abandonedCheckouts` reconciliation. Before each send, query checkout/customer/order state anew; use the current recovery URL and line items. Active checkouts are not treated as abandonment merely because an event arrived.

17. **No checkout content persistence.** Only checkout IDs and workflow state are stored; recovery URLs, contents and customer details remain Shopify-owned.

18. **Automation engine.** Linear delay/revalidate/send/stop steps, enrollment snapshots, due timestamps, stable keys, leases and a generic worker. Source failures defer safely; ambiguous submitted messages are held, never replayed automatically.

19. **Abandoned sequence.** DRAFT/OFF; 1h, then 23h, then 48h. Stops on recovery/completion, newer order creation including payment pending, invalid consent/address or suppression.

20. **Welcome.** DRAFT/OFF; actual valid consent-change event only; immediate, +48h, +60h. No email-exists/customer-created/order-exists inference and no historical welcome flood.

21. **Post Purchase.** DRAFT/OFF; live paid uncancelled order reference, default +7 days. Marketing follow-up, not a duplicate order confirmation.

22. **Win Back.** DRAFT/OFF; at least one purchase and 180 days inactive by default, configurable. Rechecks the current last order before sending.

23. **Worker.** Explicit `python crm_worker.py`; 30-second database due-work loop, renewable five-minute distributed leader lease plus independently fenced send claims. `--once` and `--seed` are available. No import-started Streamlit job.

24. **Campaign builder.** Choose native/custom audience, count/preview live eligibility, choose/edit template, preview, save draft, explicit gated test, gated schedule/send, pause/resume. Saved campaigns pin immutable content versions and expose their exact saved preview.

25. **Recipient state.** Customer ID, address hash, template version, campaign/enrollment/step IDs, status, lease, timestamps, request hash and provider ID. Unique customer/address/operation constraints; fresh consent and address at execution. No profile copy.

26. **Templates.** Nine branded HTML/plaintext templates with official 48px Sports Cave logo, escaped content, HTTPS CTA, four safe placeholders, optional product block and separate marketing footer. Support signatures remain unchanged.

27. **Resend.** Existing configuration and delivery transport reused through a marketing adapter. Stable idempotency key, one submission attempt, List-Unsubscribe headers, suppression checks, request pacing, signed provider events. No real request/send occurred in acceptance tests.

28. **Suppression/unsubscribe.** Signed receipt link; GET confirmation, POST immediate local suppression even if Shopify is unavailable. Worker syncs provider suppression and clears temporary address storage. Bounce/complaint/provider stop-state also blocks. V1 does not write consent back to Shopify.

29. **Reports.** Sends/delivered/open/click/bounce/complaint/unsubscribe metrics; campaign and automation totals, recovered/completed enrollments, worker check-in and held delivery metadata. Provider events are deduplicated and tests excluded.

30. **Revenue.** `—` when attribution is unavailable. No inferred campaign revenue or duplicated Shopify revenue. Recovery state is not claimed as causal attribution.

31. **Shopify topics.** customers/create, customers/update, customers/delete, customers_email_marketing_consent/update, orders/create, orders/updated, orders/cancelled, checkouts/create, checkouts/update, checkouts/delete. Existing orders/paid is unchanged; CRM rechecks fullyPaid on orders/updated. Existing compliance redaction configuration requires reviewed forwarding.

32. **Invalidation.** Verified minimal webhook records update a durable cache-version marker; CRM pages invalidate local display caches when it changes. TTL/manual refresh also converge on Shopify changes.

33. **Tables.** Migration defines exactly `crm_segment_definitions`, `crm_templates`, `crm_template_versions`, `crm_automations`, `crm_automation_enrollments`, `crm_campaigns`, `crm_marketing_sends`, `crm_marketing_events`, `crm_suppressions`, `crm_webhook_events`, `crm_runtime_state`. All RLS-enabled and revoked from browser roles. None were created in production.

34. **No `crm_customers`.** Confirmed by schema inspection/tests.

35. **No Shopify order mirror.** Confirmed. Existing operational Orders data was not modified.

36. **No segment-membership mirror.** Confirmed. Native membership stays in Shopify.

37. **Tests.** 63 targeted CRM tests pass, including real PostgreSQL SQL execution in an isolated in-memory fixture, all six Streamlit pages, cache/pagination, eligibility, suppression, claims, pause during validation, restart/idempotency, HMAC/Svix, immediate unsubscribe, metadata-only storage and disabled delivery. Seven existing Email/search JavaScript suites pass. All 27 changed/new Python files compile; component fixture JavaScript syntax and `git diff --check` pass. Final GraphQL queries plus registration query validate against the official bundled schema with deprecation warnings only.

38. **Browser.** Actual local OS shell with synthetic Shopify, local PostgreSQL and existing Email component using fabricated providers. Checked customer table/pagination/profile, native/custom segment preview, four draft workflows, campaign save and disabled delivery controls, branded HTML/plain previews and reports. Desktop viewports verified at 1440×900 and 1920×1080 CSS pixels. Screenshots are in `output/crm-customers-1440.png` and `output/crm-templates-1920.png`; browser acceptance uses no production data.

39. **Regression status.** Final full discovery: 3,352 tests, 131 failures, 36 errors, 70 skips. Clean archive of unchanged HEAD `493983b`: 3,289 tests, 131 failures, 38 errors, 36 skips. Comparison found **zero new failing test cases**; two archive-only errors came from existing mockup/path and Git-export assumptions. In 19 isolated relevant modules, 446 tests ran; only two existing assertions failed (Collector Vault Render-variable contract and top-bar sidebar-source contract), both reproduced on unchanged HEAD. All Email modules and Accounts & Access, navigation, search and webhook checks passed. This is not a claim that the existing repository-wide suite is green. Evidence: `output/crm-regression-comparison.json`, `output/crm-final-regression.log`, `output/crm-baseline-regression.log`, `output/crm-isolated-regressions.log`.

40. **Later migration.** Apply only `migrations/20260927093818_crm_marketing_v1.sql` after approval; not part of automatic migration startup. Then seed draft configuration explicitly. Local tests used disposable PostgreSQL only.

41. **Later worker.** Supporting Render background worker `sports-cave-crm-worker`, one instance, start command `python crm_worker.py`, reviewed code and existing private credentials. Do not create another primary web service. No worker/Blueprint/service change has been made.

42. **Later registration.** Run `python scripts/register_crm_webhooks.py` to preview existing topics, review callbacks, then separately approved `--apply` for missing topics. Existing callbacks are reported rather than duplicated or replaced. Register Resend CRM events at `/webhooks/resend/crm` on the existing webhook service. No production registration occurred.

43. **Activation.** Review → apply schema → seed OFF defaults → deploy read-only UI/webhook code with gates false → verify real Shopify reads → configure signed unsubscribe/provider events → resolve/verify webhook coverage → approve one supporting worker → internal test-only delivery → review Klaviyo cutover → separately approve one customer flow/campaign. Exact environment variables and commands are in `CRM_MARKETING_V1_SHOPIFY_FIRST.md`.

44. **Before Klaviyo cutover.** Real protected-field/API parity, event coverage, sender/domain/logo access, suppression coverage, unsubscribe round trip, internal delivery, restart/uncertain-send handling, template approval and a mutually exclusive cutover/rollback plan remain to be verified. Klaviyo was not changed.

45. **Read-only readiness.** Ready for reviewed **read-only CRM deployment testing with both delivery gates false**. Production provider behavior has intentionally not been exercised; do not activate customer marketing on the strength of fixture results alone. Workflow editing requires the approved migration. No commit, push, deployment, production migration, real send, credential change or Shopify/VentraIP/Klaviyo modification was performed. Await Nathan's approval.

## Synthetic performance evidence

Repeatable command: `.venv/Scripts/python.exe tests/profile_crm.py`. This is local Python processing against 1,000 fabricated customers, not Shopify network latency or a before/after production benchmark.

| Operation | Mean local time | GraphQL fixture calls |
|---|---:|---:|
| First 50-customer page, cold | 0.874 ms | 1 |
| Same page, cache hit (100 iterations) | 0.320 ms | 0 |
| Next customer page | 0.822 ms | 1 |
| Customer detail, cold | 0.046 ms | 1 |
| Purchase facts, cold | 0.318 ms | 2 |
| Purchase facts, cached (100 iterations) | 0.011 ms | 0 |
| Native segment members and customer batch | 1.982 ms | 2 |

The fabricated 50-customer provider page serialized to 31,951 bytes; cache contents after this benchmark were approximately 100,853 bytes. The UI sends a smaller selected field table, not all purchase history.

## Known V1 bounds

- No full-store lifetime revenue scan or inferred revenue attribution.
- Interest filters evaluate the current fetched page; complex histories are bounded and fail safely if too large.
- Audience counts are explicit paginated snapshots, not a transactionally frozen live population; final provider checks can exclude additional recipients.
- Native profile membership inspects the first 50 segment definitions; the Segments page supports further pages.
- No Shopify consent write-back; local/provider suppression must be included in cutover planning.
- Existing callback/topic conflicts require review before activation; registration never silently duplicates them.
- Supported deprecated Shopify fields remain an API-version maintenance item.
- The existing broad regression suite has unrelated failures, documented above.
