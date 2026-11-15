# Post Purchase order visibility, selection and enrolment — 13 October 2026

Task 20261011-54d8ff88, existing Sports Cave Email worktree. This chat performed local implementation/tests and SELECT/EXPLAIN-only production checks. It did not commit, deploy, publish, enrol real customers or submit emails.

## Root cause and visibility

Shopify order sync was already storing the missing orders. The audience's INNER JOIN to crm_lifecycle_customers hid orders whose optional profile enrichment had not completed. Initial production inspection confirmed **2 of the nine latest paid orders** had profiles; #SC3285 (Dale Berry) and #SC3283 both existed as PAID orders without those profiles.

Post Purchase now starts from shopify_orders and LEFT JOINs profiles and lifecycle information. Each order retains its independent Shopify order ID, including repeat purchases. All ledger orders remain visible under All, including paid, partial refund, refund, cancellation, unpaid and missing enrichment. Order name/email/customer ID provide display fallbacks only. Missing consent is UNVERIFIED, shown as Pending verification; an order email never grants marketing permission. Active suppression and irreversible redaction mask contact fallbacks, including email-hash-only redaction.

Read-only execution of the actual updated query returned **all nine**, including #SC3285 and #SC3283. A SELECT-only reconstruction restricting optional profiles to the original two returned nine orders with seven pending profiles: no production records were removed or changed for that test. During the task, external production activity refreshed all nine profiles; their cached and native Shopify marketing states were SUBSCRIBED. These observations are distinct from the initial missing-cache evidence and do not grant permission to send without fresh verification.

## Sync and flow processing

- Existing CRM preparation worker prioritizes up to five unique recent order customers ahead of the directory scan, using the existing fresh Shopify customer adapter. Per-customer durable cooldown/claims prevent duplicate lookups and retry failures safely. New/updated orders and explicitly refreshed visible customers take priority. No Shopify calls run in table rendering.
- Older source responses cannot overwrite newer consent. Redacted contacts cannot be recached, and failed cache writes are not marked VERIFIED. No consent is inferred from order contact data.
- Fixed lifecycle detection when worker metadata omits the draft: published lifecycle markers now select the actual lifecycle runtime rather than falling through to generic scheduling. Fresh order history, risk/refund/cancellation, eligibility, suppression and consent rules remain enforced.
- Automatic enrolment remains future-only. Production Post Purchase was already ACTIVE, published v1, activated **13 October at 5:45:51 pm AEDT**. **All nine inspected payments predate activation**, so automatic enrolment of those orders would be incorrect. Explicit Add to Flow is the reviewed route for selected historical orders; there is no publish-time backfill.
- The published policy still supersedes unsent older-order follow-ups when a newer qualifying purchase occurs. Older orders remain visible as independent records; their ineligibility/status is not concealed.

## Selection, table and Add to Flow

Reused crm_checkout_table without changing its HTML/JS or Abandoned Checkout behaviour. Individual/select-all/indeterminate/deselect state is now stored per flow by order ID. Only current visible keys are accepted from component events; off-page/filter selections survive ordinary rerenders without duplication. Clear selection and selected-count feedback are compact.

Columns: customer, order date, order number, email, payment, fulfilment, marketing consent, flow, Email 1–3. Frozen journey steps and actual accepted provider receipts determine Sent/Opened/Clicked; scheduling uses persisted deadlines. Disabled stages remain Disabled. Unsent stopped/ineligible stages and queued/failed manual requests provide explicit feedback. No receipt means no Sent label. Published views no longer display a blanket Draft-only message.

Add to Flow requires an active published flow, administrator permission and explicit confirmation. It batches audited requests into the existing CRM runtime-state queue, recording actor/order/customer/published version. The existing worker claims requests and freshly verifies readiness, signed payment, customer/order membership, consent, suppression and lifecycle eligibility. Transactional version/status checks, request expiry and existing unique journey identities prevent stale approval or repeated requests from replaying emails. It preserves the original paid-event timestamp plus configured delay; it does not reset or bypass delays. Draft selection works but enrolment is rejected. Submitted/accepted history remains preserved.

The existing eligible-customer preview selector/renderer/test-send system is retained. Post Purchase candidate lookup can freshly verify an uncached order customer rather than hiding that order. Cached preview facts never authorize delivery. Final native unsubscribe, provider suppression, recipient verification and approved test-destination controls remain mandatory. No production preview/customer data was used in local browser fixtures.

## Content and consent preservation

Read-only production metadata confirmed the current sequence, which this implementation did not edit:

- Email 1: Welcome to the Collection; subject **You're officially a Sports Cave collector**; payment anchor; **10,800 seconds**; enabled.
- Email 2: Display Your Sporting Legacy; delivery anchor; 604,800-second configured offset; disabled.
- Email 3: Build Your Collection; payment anchor; 3,888,000-second configured offset and existing fulfilment guard; disabled.

HTML, edition language, purchased-artwork/collection bindings, templates and immutable draft/published separation remain unchanged. Promotional collector content requires verified marketing subscription. Unsubscribed, pending and missing-profile purchasers remain visible but cannot obtain marketing permission from their purchase. Necessary Shopify order/shipping/delivery notifications remain under their existing configuration. No extra transactional email, duplicated notification or promotional-to-transactional relabelling was added.

## Verification and performance

- **290 tests passed**, no failures/errors/skips, on fresh disposable PGlite PostgreSQL with repository SQL/migrations, synthetic Shopify facts and blocked external transport; 38.981 seconds. Log: .tmp-preview-performance/post-purchase-verified-tests.log.
- **40 focused tests passed after final profile-cache refinements**, 6.643 seconds. Log: .tmp-preview-performance/post-purchase-profile-verified.log. Covers missing profiles, all-market rows, repeat orders, refund/cancellation visibility, redaction, fresh unsubscribe, Draft rejection, explicit durable manual enrolment, retained three-hour deadline/disabled stages and future-only worker metadata routing.
- Broader coverage includes purchased/variant images, collections, editing/reopening, selected-customer isolation, test-address restrictions, native unsubscribe, publication rollback/pause/resume, and Abandoned Checkout regressions. These remain fixture/integration evidence, not actual production sends or live artwork screenshot certification.
- Actual Chrome + Streamlit + PostgreSQL browser test passed on 55 synthetic orders: individual/header selection, indeterminate header, deselection, search/filter/page persistence, explicit durable confirmation, Draft-disabled action, and 390/320-pixel layouts. Log: .tmp-preview-performance/post-purchase-browser-complete.log.
- Production PostgreSQL unfiltered 51-row page EXPLAIN ANALYZE: old query **40.956 ms**, new **14.665 ms** execution; planning 10.234/5.150 ms. Nine-order query: 12.888/6.121 ms. These are individual read-only measurements, not latency percentiles or a controlled load benchmark.
- Local nine-order SQL measured approximately **5.6 ms** in the final focused run. Browser first table after opening the panel ranged **845–1,428 ms** across local samples; warm page return **200–215 ms**. Full fixture startup/first table ranged 2.9–4.7 seconds after warming and includes constructing/publishing synthetic fixtures. No production browser timing claim is made.
- The lifecycle reader reuses the existing bounded cache/futures, with a Post Purchase-only 150-ms initial wait budget. Abandoned Checkout's existing 50-ms budget is unchanged. Previous rows remain visible during same-page refresh, caches are session/criteria/page scoped and bounded, and only fragment reruns are used for selection/polling.
- Initial tests caught an omitted customer order count and fixture timestamp precision/global-data assumptions; fixed and rerun. Optional thumbnail prewarming still logs browser_runtime_unavailable locally without blocking HTML/publication tests.

## Operational state and remaining limits

An external action advanced this worktree from d6405494 to **1c3c0744** during the task, committing initial changes outside this chat. Production cache state also changed externally. This chat did not execute those commits/deployments and preserved their contents; later refinements and tests remain local. Review the exact final candidate before any further release.

Read-only runtime records showed healthy delivery/publication consumers and Post Purchase paid trigger AVAILABLE. ORDERS_FULFILLED and the Welcome consent-update subscription remain missing. They do not block the current payment-only Post Purchase sequence; enabling fulfilment-dependent stages requires their verified webhook. Production Resend authentication/domain status and real customer delivery were not independently exercised. The final local refinements, live browser artwork acceptance and an explicitly authorised test send still require separate review/approval as applicable.

## Files/components changed for this task

crm_lifecycle_audience.py; crm_post_purchase_audience.py; crm_lifecycle_ui.py; crm_lifecycle_enrollment_requests.py; crm_lifecycle_sync.py; crm_lifecycle_runtime.py; crm_automation_runtime.py (lifecycle dispatch only); crm_flow_preview.py (Post Purchase adapter only); crm_automation_analytics_ui.py (optional lifecycle wait budget).

Tests/fixture: tests/test_crm_post_purchase_audience.py, tests/test_crm_post_purchase_ui.cjs, tests/fixtures/crm_post_purchase_ui.py. Documentation: this report. Some initial runtime changes are now included in the externally created commit noted above.

**Local implementation ready for review; no production release or real enrolment approval is implied.**
