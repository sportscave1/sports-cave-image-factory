# Orders companion 1.7.30: verification and remaining consolidation work

## Released scope

- Original Fulfilment mappings remain unchanged: Black/Oak/White framed CFP and Unframed FAP, S=A4, M=A3, L=A2, XL=A1. Oak selects Natural. All 16 blank-product selection/readback cases pass.
- Artwork still uses the browser editor. Live item PATCH remains blocked: it previously cleared the product and cannot safely round-trip hidden editor metadata. Product selection is independently read back before artwork upload.
- Restart can retire a handoff interrupted before its Save permit only after fresh supplier readback proves the same empty item, product and business details. A started or uncertain Save is never uploaded again blindly.
- Companion batch capability checks up to 20 separately allocated items in one browser pass. Shipping, tax and inserts are inspected once; exact item ID, product/frame and Excellent quality are checked for every item. Server artwork/edition/address checks remain per item. A missing, duplicate, wrong or failed item prevents the existing one-order submission fence from submitting.
- Same supplier-order rows are consecutive, with navigation between their numbered editions in the review panel. This is grouping for display and QA; each edition retains its original certificate/account identity.
- Existing countdown, payment, production and certificate timing are unchanged. No resume/Send now action is added.

## Validation

152 focused Python tests and 34 Node companion/UI tests passed. Includes all 16 mapping selection cases; batch success and missing/duplicate/wrong/poor-quality/changed-order failures; no repeat submission; per-edition production certificates; interrupted-before-Save recovery.

Read-only live audit found 11 non-complete preparation records and no repeated independently identified Shopify customer across separate order references. No live consolidation or cancellation was performed.

## Not implemented: merging separate Shopify orders

Automatic cross-order consolidation/cancellation is NOT enabled by this release. Do not infer it from the same-order grouping or batch QA feature.

Prodigi v5 only permits adding/editing items on drafts. A submitted order in its edit countdown requires the native dashboard. The dashboard exposes Add another item, but its Options menu has Duplicate/Remove rather than an order move/merge action. A reliable native copy, independent new-item binding, all-copy QA and redundant-source cancellation workflow still needs implementation and acceptance before it can be enabled. Cancellation retains supplier history; there is no hard-delete order endpoint in this integration.

Required constraints for that follow-up: same independently verified Shopify customer ID, complete matching delivery recipient/address and shipping intent; oldest eligible unpaid target; fresh unpaid/production-history checks on both sides at each write; no name-only matching; preserve original Shopify orders, edition allocations and certificate/account destinations; commit durable item-add and cancellation intents; reconcile uncertain responses without duplicate items or cancellations; cancel source only after every target copy is independently verified; never reset/resume/change the target countdown or touch paid/production orders. Test against a genuine eligible repeat-customer case before enabling.

Primary supplier references: https://www.prodigi.com/print-api/docs/ ; https://www.prodigi.com/faq/ordering/ ; https://support.prodigi.com/hc/en-us/articles/13157931074076-Can-I-pause-orders
