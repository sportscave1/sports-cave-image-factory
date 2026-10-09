# Shopify discounts in the Email Editor — V2 delivery report

Implemented locally on 9 October 2026. No commit, push, deployment, live automation publication, customer email, Shopify discount/checkout mutation, permission change, theme change, or Edition Ops change was performed.

## Confirmed failures and repairs

**Streamlit lifecycle:** the previous `crm_discount_ui.repaint()` called `st.rerun(scope=COMPOSER_TARGET or 'fragment')` from the composer/fragment body after starting a search and after consuming its future. The selection path did the same. A named fragment rerun is only legal from a callback on the production runtime shown in the screenshot. The fallback is also illegal during an initial full-script run. The unchanged HEAD `repaint` function was replayed with Streamlit AppTest and reproduced the latter exception. Local Streamlit is 1.58.0 and lacks named-fragment support, so the production-specific wording is confirmed by the supplied traceback rather than an identical local version.

The replacement uses the existing section component's supported `on_change` callback. It contains no imperative `st.rerun` calls. The component emits bounded completion polls only while the picker is open and a request is pending. Completion, timeout, close and error stop polling. Search results live in per-editor session state; generations prevent an obsolete future from replacing newer results. The existing composer fragment owns updates, with no new full-application refresh loop.

**Missing results:** opening the previous selector did not request an initial page. Its explicit search/completion path aborted at the invalid rerun before results could reliably display. Its quoted exact terms also did not implement prefix search. Read-only live requests establish that the underlying discount query is valid and that MYCAVE5 exists. They do not prove the deployed OS app has permission. No unverified authentication or Shopify outage is claimed as the cause.

Malformed responses, missing permission, transport failures and actual empty pages now have distinct outcomes. Previous results remain visible on failure, with selection disabled until a successful refresh. Prefix queries use escaped unquoted word prefixes: live testing found that a quoted prefix followed by `*` returned no match.

## Live Shopify evidence and permissions

Fresh read-only exact lookup, title search and `MYCAVE*` search found:

| Field | Verified value |
|---|---|
| Code / title | MYCAVE5 |
| Shopify identity | `gid://shopify/DiscountCodeNode/1558680568115` |
| Status | ACTIVE |
| Type / amount | Fixed AUD 5.00 off |
| Application | Once per order, eligible All Sports Wall Art collection |
| End date / minimum | No end date / no configured minimum requirement returned |
| Combinations | Product: no; order: no; shipping: yes |

The repository defaults to Admin API **2026-04**. Search and bulk-code operations passed Shopify's schema validator for that version, including the required `read_discounts` scope. Runtime permission checks accept Shopify's read access or its corresponding write grant; this feature performs only reads.

The connected **Shopify ChatGPT MCP App** has discount access. It is a different installation from Sports Cave OS. Local Sports Cave OS Shopify credentials/domain were unavailable, and `appInstallations` was denied to the connector. Therefore the actual production OS app scopes and configured API version remain **unverified**. No permissions were changed. Existing checkout/customer read access remains necessary for send-time verification.

## Editor workflow and presentation

All Recovery Discount controls have been removed from Settings: heading, automatic-apply toggle, selector, clear control and explanatory/search panel. Settings retain their existing email controls.

Use **Editor → Add section → Add Discount**. An initial page loads asynchronously without a search. The compact list shows code, actual value, type and status. Selecting an available code immediately inserts a dark, gold-accented HTML section. Nothing is preselected for any email.

The section uses the existing rename, HTML editor, move, duplicate, hide/show, delete and undo tools. Typography, text, colours, borders and spacing are editable in its HTML. A Change button reopens the same selector. Shopify's code/value remain authoritative through `{{discount_code}}` and `{{discount_value}}`; the default includes both. Missing authoritative tokens and unverified hardcoded amount/percentage/type claims in the offer section block preview/publication/delivery while retaining editable draft text. This is structured validation, not a semantic guarantee about every possible manually authored sentence; the existing copy review still applies.

Each email owns one selected offer. Duplicated presentations share that offer; changing it updates all presentations while preserving authored HTML. Hiding/removing the last visible offer clears the draft's `recovery_discount`. Restoring it restores the association. Dependent subject/preview tokens may remain in a saved draft for repair, but strict publication and rendering prevent them reaching customers unresolved.

Old saved selections become editable sections in the editor copy before its clean baseline is established. Opening alone does not save a revision. Existing persisted published snapshots and frozen journeys are not migrated or rewritten. A later genuine draft edit uses normal draft persistence.

## Search, supported types and responsiveness

- Percentage and fixed amount: verified percentage or currency amount, including per-item qualification.
- Free shipping: accurate offer type, subject to Shopify conditions.
- Buy X Get Y: Shopify's actual summary.
- App-managed codes: explicitly labelled app-calculated, with value determined at checkout; no invented amount.
- Automatic discounts are excluded. Unknown/unverifiable types are not selectable. Scheduled, inactive, expired and reported exhausted codes are disabled.

Search/browse reads at most **15 groups and 20 codes per group** per page. Exact-code lookup reaches bulk codes beyond the first page. Shopify explicitly excludes bulk codes from its global code filter: search a bulk group by title, then use **Browse codes** for prefix search/pagination within that group, or enter the complete code globally. A changed group search starts at a new cursor; cursors from different queries are never mixed. This avoids an unbounded full-store scan.

Existing metadata caching remains bounded to 60 seconds, 64 entries and 2 MiB. Reopening expired display state refreshes it; Refresh bypasses result caching. There are two worker threads and four total running/queued slots, a 30-second UI deadline, and the existing Shopify request timeout/retry limits. Late results cannot overwrite a timed-out/newer search. Ordinary page opening and unchanged preview refreshes perform no new discount lookup. Opening/searching do not save drafts. Search is debounced 350 ms, and completion preserves focus and list position.

Actual local timings, not production latency:

| Measurement | Before | After |
|---|---:|---:|
| Cold search, three fixture reads at 20 ms each | 61.295 ms | 60.970 ms |
| Repeated cached search | 0.029 ms | 0.032 ms |
| Additional cached API requests | 0 | 0 |
| Existing render without discount | 0.919 ms | 0.891 ms |
| Render with existing discount substitution/link handling | 1.089 ms | 1.087 ms |
| Render including the new editable offer section | N/A | 1.579 ms |

Final headless Edge run: selector visible **198 ms**, initial selectable results **1,348 ms**, debounced search through selectable results **1,500 ms**, with a deliberate 600 ms fixture response delay. Earlier completed runs were similar. The production crash has no meaningful successful baseline UI completion time. These measurements show bounded asynchronous behavior and negligible change to the existing render path; they do not claim Shopify requests themselves became faster.

Reproduce timings with `python -m tests.email_discount_benchmark`. Browser test: `node tests/test_crm_discount_ui.cjs`, using the disposable fixture on port 8543 and local SQL fixture on 8893.

## Checkout links, personalization and delivery safeguards

The established verification and delivery architecture is reused. A render-only copy converts the bound offer presentation into existing HTML-section form so all recovery-link, tracking and HTML checks also apply inside editable offer HTML. Saved sections retain their Shopify binding.

All Recover Checkout elements use the same authorized, verified original Shopify recovery destination. The existing implementation adds one encoded discount parameter and retains original identity, query bytes, fragments, products, variants and quantities. It does not rebuild a checkout. Wall Preview destinations remain separate. Preview displays the selected code/value and explicitly leaves eligibility to Shopify; inclusion in a URL is not represented as confirmed application.

Before a promotional send, current Shopify facts are read again. Existing holds remain for removed/changed/expired offers, reported usage exhaustion, known unmet minima, unavailable products, identity mismatches, verification failures and existing code conflicts. Standard automatic promotions retain Shopify's best-eligible-offer rules; product-code/Buy X Get Y and opaque app-promotion conflicts retain conservative safeguards. MYCAVE5 is not promised to stack with the 15% multi-buy offer. Shopify retains authority over customer/product/market eligibility and final combinations.

Discount variables remain supported in subject, preview text and HTML, with escaped rendering. Invalid offers are held rather than silently removed from a promised promotional email. Scheduling, consent, unsubscribe handling, purchase cancellation, Resend transport, webhook/enrollment behavior and Edition Ops were not changed.

## Verification results

**263 Python tests executed: 261 passed; two existing baseline assertions failed.** No skipped tests in these final suites. Mocked provider transport and disposable PGlite SQL were used; no production database was used.

| Suite | Result |
|---|---|
| Discount V2, existing discounts, actual mocked delivery, component JSON, section/image/name behavior | 67 passed |
| Native automations, personalization, recovery elements, checkout, lifestyle images, frame banner, publication and automation stability | 155 passed |
| Existing campaign sections and preview stability | 23 passed, 2 baseline failures |
| Edition allocation-integrity and stability fixtures | 16 passed |

Baseline failures, left unchanged:

1. `SectionPersistenceTests.test_ui_defaults_rerun_and_edits_persist_without_hidden_conversions` expects no `html_sections` although HEAD's editor creates default header/footer HTML. Reproduced with all changed application Python modules replaced by their unmodified HEAD versions in an isolated temporary import directory.
2. `PreviewStabilityTests.test_automation_only_polling_and_debounce` requires an obsolete literal `not any(s['type']==BLOCK`. That literal is absent in HEAD as well; the other preview stability checks pass.

The full headless Edge flow passed at 1440×950 and 390×950: Settings removal, initial asynchronous browse, prefix search, focus preservation, close/reopen, insertion, visible rendered offer, exact saved HTML, moving, hide/restore, deletion, no runtime exceptions, no horizontal mobile overflow, unchanged Email 1/2 and unchanged published version. Database snapshots were identical before and after opening/searching. The original illegal full-run fragment repaint was separately reproduced from HEAD.

Tests cover stale/late futures, timeout recovery, explicit errors versus empty pages, bounded/cache refresh behavior, bulk cursors, all supported type families, changed/invalid offers, existing discount conflicts, recovery URL bytes and fragments, custom/native/lifestyle recovery links, Wall Preview separation, editable tokens, immutable journeys, Email 3-only delivery, purchase cancellation, held sends and duplicate-send prevention. Python compilation, JavaScript browser execution and `git diff --check` passed.

## Files changed for this request

Application:

- `crm_discount_ui.py`, `crm_discount_api.py`, new `crm_discount_section.py`
- `components/crm_sections/discount.js` (new), `composer.js`, `index.html`, `style.css`
- `crm_campaign_page.py`, `crm_section_ui.py`, `crm_component_json.py`
- `crm_middle_sections.py`, `crm_email_editor_context.py`, `crm_recovery_discount.py`
- `crm_automation_definition.py`, `crm_automation_store.py`, `crm_personalisation.py`

Tests/report:

- New `tests/test_crm_discount_editor_v2.py`
- `tests/test_crm_discount_delivery.py`, `tests/test_crm_discount_ui.cjs`
- `tests/test_crm_component_json.py`, `tests/email_discount_benchmark.py`
- `docs/EMAIL_DISCOUNT_EDITOR_V2.md`

Existing unrelated edits in `meta_review_creative.py` and `tests/fixtures/refresh_ui.py` were preserved.

## Rollout requirements and remaining limits

No migration, new dependency, new environment variable or new service is required. A separately authorized deployment must include both the application and email-worker code before any new section format is published. Do not roll a worker back to code that predates this section type while published new-format emails are queued.

Confirm the deployed Sports Cave OS app's API version and existing discount permission before rollout; permission changes require approval. Live verification here used the separate connected app. No real checkout application or customer email was tested. Shopify eligibility is ultimately evaluated at checkout, and app-managed functions do not expose a universal static value. Global partial bulk-code search is limited by Shopify as described above. Gmail/Outlook client certification was not performed.

After a separately approved deployment, choose a discount in the desired email and use the existing review/publication workflow. MYCAVE5 was verified only; no live Email 1, 2 or 3 was selected, edited or published by this task.

## Verified references

- [Admin discount search, supported filters and bulk limitation](https://shopify.dev/docs/api/admin-graphql/2026-04/queries/discountNodes)
- [Discount code groups](https://shopify.dev/docs/api/admin-graphql/2026-04/objects/DiscountCodeNode)
- [Shopify search syntax](https://shopify.dev/docs/api/usage/search-syntax)
- [Original abandoned-checkout recovery discount links and existing-code warning](https://help.shopify.com/en/manual/discounts/discounts-for-abandoned-checkout-recovery-emails)
- [Shopify combination rules](https://help.shopify.com/en/manual/discounts/discount-combinations)
