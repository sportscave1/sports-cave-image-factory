# Blank-product upload handoff root cause — 22 November 2026

## Observed failure

Two new allocations stopped at artwork.page with `An existing editor requires manual review.` Both had independently verified product-selection receipts, still-empty required print slots, and an unused artwork Save permit. This is a deterministic stage-transition defect, not an incorrect variant mapping, poor image quality or the number of editions.

Prodigi can automatically open Image Editor after choosing a previously blank product. Product selection waits for the correct persisted item row, but that row can coexist with the automatic editor. Reusing the worker tab carried the editor into upload, which correctly rejected an unexpected open editor. Previous fixtures closed the product picker and showed the row without modelling the automatic image editor. Sequential scheduling alone therefore did not fix this path.

## Corrected transition

The server issues `selected_empty_product` only for a live, exact-item upload with a verified product-selection receipt and no existing artwork. Source identity, allocation, variant and supplier draft are rechecked as before. A new companion clears the automatic shell by reloading only its own reused exact-order tab, before transferring/uploading any bytes to the supplier. It waits for a different content-script page instance, preventing the old page's ready response from racing navigation. A new tab is already clean and needs no reload. Ordinary artwork, full Reset, certificate and QA handoffs cannot use this authority. The unexpected-editor guard and single-use Save permit remain intact.

Companion 1.7.37 advertises the fixed transition. Only that capability enables narrow recovery of the known page-stage error: verified product selection, unused Save permit, no submission and an unchanged empty supplier item are required. Existing source, address, artwork or business-state changes stop recovery. There are no blind Save retries or paid/submitted order resets. Supplier countdown/preferences are unchanged.

## Live follow-up: item QA must not wait for whole-order controls

The first repaired upload completed and independently verified its saved artwork. The subsequent old per-item QA then timed out at `QA inserts` while two sibling products were unprepared. Although scheduling was sequential, that QA still tried to inspect order-level controls after each individual image. This is a second stage-contract defect, not another upload failure.

Companion 1.7.39 supports explicit item-only QA: exact item ID, SKU/frame/size, saved numbered image and full fit, Excellent rating and customer address are checked immediately. It neither reads nor changes shared inserts/shipping/tax. Those remain pending, and final QA is explicitly incomplete. The complete set of required check keys, final order hash, tax evidence, fresh grouped readback and one submission fence are still mandatory before submitting. Once all artworks are uploaded, the existing combined QA checks every item plus shared controls. An older companion cannot claim this item-only handoff.

The old untouched item-only inserts timeout can be recovered only by a capable companion after independently checking that the verified artwork and entire pinned supplier business state have not changed. It retires the unused QA receipt, not the artwork receipt. PSD repair blocks remain separate and are never converted into passed QA.

The second recovered upload also saved and independently verified successfully, but its UI retained an Image Editor when QA started. All new QA handoffs now explicitly authorize a fresh read of the verified saved order. The same worker-owned, exact-order, different-page-instance fence clears stale post-Save UI before QA. No new file download or upload occurs for QA. Recovery covers only the precise unused QA editor/inserts failures, and still verifies unchanged persisted source, image and supplier business state.

## Separate artwork prerequisites

Two additional editions in the three-item order have no generated JPG because their PSD preparation reports `Exactly one visible, editable edition-number layer is required.` Their repair requests are already queued. This release does not fabricate a numbered print, approve an invalid PSD or claim those editions have passed QA. They must finish the existing repair/preparation pipeline before whole-order submission.

## Regression coverage

Tests now model variant selection automatically opening an editor, worker-tab reuse, the old page replying ready after reload, fresh-page upload and subsequent QA. Server tests verify the empty-item authority and recovery, including negative cases for changed assets, recipient, used permit, recorded submission and unrelated errors. Existing multi-edition, exact-item, uncertain Save, delayed-control, Reset and queue-notification suites are rerun. All tests use synthetic local data; genuine customer orders are observed only through authorised production diagnostics and the existing companion.
