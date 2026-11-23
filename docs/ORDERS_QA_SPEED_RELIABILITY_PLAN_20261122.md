# Orders QA speed and reliability plan — 22 November 2026

## Outcome of the audit started today

The release candidate is Companion **1.7.40**. The user subsequently authorized implementation and deployment of all six phases. Implementation and local release checks are complete; runtime activation and genuine-order acceptance are separate release checks. See [implementation evidence](ORDERS_QA_1740_RELEASE.md). Keep Prodigi preferences/countdown unchanged.

The focused baseline passed **159 Python checks** covering product selection, upload verification, individual and grouped QA, submission, transaction lifetime, Reset, scheduling and real Streamlit fragment contexts. Four additional synthetic scaling cases passed: **163 distinct Python checks in total**. The final companion suite passed **62 Node checks**. They exercise real companion functions with synthetic browser controls and intercepted service boundaries; they are not evidence of production network latency or universal supplier success.

Three additional false-failure risks were reproduced and corrected locally:

1. A product row can appear before its image-quality badge. QA now waits for a nonempty badge on the exact item, re-resolving the row if React replaces it. Immediate evidence adds no fixed delay. A Poor rating is preserved as Poor for server verification, never promoted to Excellent.
2. A worker-owned tab may retain the image library's allowed URL filters. Reload alone preserves those filters, while QA pins the clean order-detail URL. A fresh verified handoff now navigates that owned exact-order tab to the canonical URL and waits for a new page instance. Other tabs are not claimed or navigated.
3. Closing inserts can temporarily remove or disable the shipping selector. QA now waits for its return and for the selected service after rerender. Multiple selectors still fail explicitly. Quote currency, price, cheapest-service policy and final server readback checks remain intact.

The existing flow remains: **variant → numbered JPG upload → individual item QA → next product → shared order QA → one guarded submission**. Per-item QA does not wait for other products' inserts/shipping/tax controls. Final QA still verifies all exact items and shared requirements before submission. Saved images and uncertain writes are reconciled rather than blindly uploaded again.

## Measured scaling baseline

This measures the final submission worker against synthetic already-verified fixtures using local PostgreSQL-compatible storage. It does **not** time artwork preparation, browser uploads, a whole QA cycle, or Prodigi's live network. One sample per size is sufficient for a read-count regression, not a latency percentile.

| Products | Supplier order reads | Source checks | Submit calls | Local elapsed |
|---:|---:|---:|---:|---:|
| 1 | 3 | 2 | 1 | 19.22 ms |
| 2 | 3 | 4 | 1 | 23.55 ms |
| 5 | 3 | 10 | 1 | 31.69 ms |
| 10 | 3 | 20 | 1 | 49.73 ms |

The useful invariant is constant supplier reads, linear source checks and one Submit per order. The three reads preserve two independent preflights and acknowledgement; do not remove those safeguards merely to improve a benchmark.

## Phase 1 — release the tested stability fixes

**Deliver:** reviewed 1.7.40 package with unchanged permissions; delayed badge/selector handling; clean owned-tab handoffs; current per-item QA and recovery. Retain the previous package for rollback. Release only under explicit deployment authorization, then activate the extension and confirm its runtime version.

**Acceptance:** observe a genuine single-product order and an eligible multi-product order through all item checks, shared QA and one submission. No Reset or repeat upload of an already verified image. An order blocked on an actual PSD preparation defect waits for the existing repair pipeline. Do not reset a submitted/paid order or create real purchases to manufacture acceptance.

## Phase 2 — make every wait and failure observable

**Deliver:** durable stage start/end times, current item/total, active companion version/capabilities, last successful checkpoint, safe failure code, next retry time and queue age. Show distinct Waiting, Retrying, PSD repair and Review states. A control still loading should not look like failed print quality. Preserve the table's selection/scroll and expose deeper diagnostics only when requested.

Record receipt → mirror → allocation → PSD/JPG readiness → companion pickup → variant → upload → item QA → shared QA → submission → paid/production → certificate. Separate network/PSD/browser-render time from software scheduling time. Keep secrets and customer addresses out of diagnostic logs.

**Acceptance:** every active job has a current stage; status reaches Orders within five seconds of a committed change; an operator can identify the last confirmed action and next safe action without reading raw logs. Collect real p50/p95 timings before setting end-to-end speed claims.

## Phase 3 — replace avoidable sleeps with positive readiness

**Deliver:** exact-item, event-driven DOM readiness where practical, with bounded deadlines and a polling fallback. Add explicit readiness for quality, catalogue, image editor, inserts and saved shipping/tax. Replace fixed orientation/fit/shipping delays only where a positive persisted/UI condition can replace them. Keep fresh-page identity fencing and no parallel native writes.

**Acceptance targets:** scheduling overhead p95 below 500 ms once required inputs are ready; no added delay for immediately available quality/shipping; late controls recover without repeating Select/Save. These are targets to measure, not current production results. Permanent missing controls, changed identity or unavailable supplier access remain diagnosable review states.

## Phase 4 — shorten queue pickup and keep busy orders fair

**Deliver:** prioritize continuation of the active item's upload/QA, then the next ready item in that order; prevent one PSD-repair order from blocking unrelated ready orders. Retain one native writer, notification replay and fallback polling. Deduplicate incoming events by immutable job/allocation identity. Reuse verified local metadata within one phase while independently revalidating before writes. Do not add image prefetch until memory/network measurements justify a strict bound.

**Acceptance targets on a healthy, idle system:** receipt-to-mirror p95 under five seconds; committed ready work to idle-companion pickup p95 under five seconds; table arrivals visible within five seconds. Report busy queue time and PSD rendering separately. No extra whole-order reads as product count grows; no duplicate work from repeated webhook/notification delivery.

## Phase 5 — controlled recovery and fault injection

**Deliver:** classify read-only transient failures separately from data defects and uncertain writes. Retry bounded read/verification failures with backoff. Preserve a committed Save/Submit intent and independently reconcile it before deciding what can resume. A retry must name the exact stage/item and retain completed work. Keep repaired PSDs tied to their correct source revision and allocation.

**Test matrix:** 1/2/5/10 products, identical SKUs with different editions, late controls, changed/replaced DOM rows, image-library URLs, tab closure/navigation, extension restart, network disconnect, stale token, duplicate notification, Reset during a readback, changed source/address, unavailable Express, poor quality, empty inserts, uncertain Save, uncertain Submit, production transition and certificate retry. Include a thousand synthetic queue deliveries with duplicates and interruption points.

**Acceptance:** zero wrong-item or duplicate submissions across the fault matrix; no payment/production action from incomplete item QA; safe transient recovery does not reupload a verified image; one order's genuine data problem does not stop the ready queue. No automatic global unpause or countdown change.

## Phase 6 — canary release and performance budget

**Deliver:** run the targeted tests before every companion/server release; maintain fixture coverage for each real incident; release to the paired desktop with a known version and observe genuine eligible orders before broad acceptance. Compare p50/p95 stage time, queue age, automatic recovery rate, review reasons, API read count and peak browser memory against the measured baseline. Keep server and companion rollback compatibility explicit.

**Acceptance:** no new correctness regressions; all new versions have a verified runtime handshake and completed single/multi-product acceptance; no unexplained stuck jobs; read-count budgets hold. Expand observation from the first eligible orders to a larger representative batch. A browser/Prodigi outage is surfaced as a retry/wait rather than hidden as a success. Certificate completion is confirmed only after the supplier's paid/production state and successful customer-account upload.

## Recommended sequence

Ship Phase 1 when authorized, then implement Phase 2 before further speed tuning. Use those timings to choose Phase 3's highest-cost waits and Phase 4's real queue bottlenecks. Complete the fault matrix before broad rollout. Treat actual PSD defects, identity conflicts and uncertain writes as meaningful conditions; reliability means correct, recoverable processing rather than forcing every check green.
