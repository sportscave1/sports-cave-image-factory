# Post Purchase Orders panel — local verification, 13 October 2026

Task `20261011-54d8ff88`, owner `me/email-flow-fix`. No commit, deployment, publication, real customer enrolment or email send was performed.

## Findings and changes

The Orders disclosure was inside the fragment that refreshes its table. Every 15-second component refresh changed the audience generation/cache key, forced another database read, and explicitly reran the fragment again. This coupled expander reconstruction to background events and defeated the existing 30-second read cache. Selection also required another explicit rerun after its component event. The table discarded off-page selections in its client projection, so its header could not clear the complete selection.

The isolated pre-change browser baseline stayed logically open for 35 seconds. The exact reported production close/reopen symptom was **not reproduced locally**, so production causality is not claimed solely from code inspection. The identified refresh and state-ownership defects were repaired, and sustained browser stability was verified after the change.

- The Post Purchase expander now belongs to the page. Its refreshing table is a child fragment. Background table events do not recreate the expander; only a user toggle changes its open state.
- Existing 15-second visible-table updates now reuse the 30-second bounded read cache. Pending reads use the existing one-shot settlement mechanism. Valid rows remain visible during refresh/failure. A genuine initial read failure offers a compact Retry action; there is no routine Refresh audience control.
- Selection is consumed in the component callback before the toolbar renders, without an additional explicit rerun. Page/filter context fences reject late events from another result set. Checkbox deselection can clear all selected orders across pages. Ordinary row deselection retains off-page selections.
- The compact toolbar is Search | Status | Sort | calendar popover | Add to Flow. It uses 32 px controls, hidden accessible labels and a visually clipped accessible date-filter name. It occupies one row on desktop and wraps on narrow screens.
- Visible columns are Checkbox | Customer | Order date | Order | Fulfilment | Flow | Email 1 | Email 2 | Email 3. Further stages remain dynamic. Email, Payment and Marketing consent are retained in the ledger/query and customer diagnostics, not displayed as table columns.
- Removed Refresh audience, Clear selection, selection-count/help text and the routine draft/publication help paragraph. Errors and the existing enrolment confirmation remain.
- Order-specific table styling uses 32 px rows, Segoe UI, compact cells and existing sticky headers/frozen customer columns. Abandoned Checkout receives no order-specific styling or selection behaviour.

## Safety

Add to Flow requires locally known candidate eligibility, an active published flow and an administrator. Its tooltip explains unavailable actions. Only explicitly confirmed requests reach the existing worker, which still performs fresh Shopify payment, consent, suppression, cancellation and publication checks. The 100-order limit, idempotency and accepted-send protections remain. Draft selection and customer details do not enqueue delivery.

No order syncing, audience SQL, email content, personalised product bindings, schedule, three-hour Email 1 delay, disabled follow-ups, publishing or delivery implementation was changed.

## Verification and performance

- **49 focused tests passed**, zero failures or skips: order-ledger visibility and enrichment, explicit confirmation, consent/pause rejection, paid-event future-only enrolment, immutable publication, checkout purchase exits and normal Abandoned Checkout recovery. Presentation tests cover global deselection/replay, stale page events and candidate gates.
- Real Chrome/Streamlit panel checks at 1440 px and 390 px cover individual/multiple selection, Select All, cross-page deselection, search, Status/Sort, keyboard date filtering, pagination, customer details and the confirmation dialog (cancelled without enrolment).
- Desktop idle check: **185 seconds open**, zero closures and zero iframe remounts during background updates. The selected checkbox and 220 px internal scroll position remained intact. Manually collapsed Orders remained closed for **35 seconds**.
- Desktop controls occupy one row, with no document overflow; mobile scroll remains inside the table. Keyboard labels, focus indicators and the existing confirmation safeguards remain.
- The existing Abandoned Checkout component browser regression passed: dynamic columns, acceptance evidence, countdowns, selection/details, DOM retention, sticky scrolling, cleanup and bounded polling. Its rows remain 34 px.
- Synthetic 50-row component benchmark: median update **0.3 → 0.2 ms**, p95 **0.5 → 0.3 ms**, order row height **34 → 32 px**. These are browser DOM update timings, not production end-to-end measurements. An empty filtered page also supports clearing off-page selections.
- Final panel run: warm reopening **169 ms desktop / 137 ms mobile**; two selections **417 / 404 ms**; individual local audience queries **5.9–59.3 ms**. Cold component opening was **4.264 seconds desktop / 1.589 seconds mobile**. Earlier samples ranged around 3.1–3.2 seconds. First-open Streamlit/component latency is not claimed to be instantaneous. The desktop fixture recorded 13 audience reads across all interactions and its sustained refresh window; the shorter mobile run recorded seven.
- Previously each 15-second refresh invalidated the read key. It now observes the existing 30-second TTL, avoiding forced duplicate reads and keeping one in-flight read per current key. Shopify request count for routine table refresh remains **zero**.

All browser/database facts are fabricated local fixtures using a disposable loopback PostgreSQL engine. No production connection or provider transport was used. Live OS-shell behaviour and production latency require an approved deployment/verification; no production repair is claimed here.

## Files and readiness

Application files: `crm_lifecycle_ui.py`, `crm_post_purchase_audience.py`, `components/crm_checkout_table/index.html`.

Coverage: `tests/fixtures/crm_post_purchase_ui.py`, `tests/test_crm_orders_panel.py`, `tests/test_crm_orders_panel_ui.cjs`, `tests/test_crm_orders_table_ui.cjs`.

Report: `docs/POST_PURCHASE_ORDERS_PANEL_20261013.md`.

Ready for local review after focused tests and browser checks. Deployment requires separate approval. The unobserved original production collapse and cold Streamlit opening latency remain explicit verification limits.
