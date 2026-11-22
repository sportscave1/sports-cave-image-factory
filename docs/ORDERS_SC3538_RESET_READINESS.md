# SC3538 reset readiness diagnosis

Allocation972, Sweetness / Walter Payton, edition57/100, Black/M, GLOBAL-CFP-A3. Read-only live inspection on2026-11-23 Sydney.

## Evidence

The earlier attempt selected the correct product, then stopped at artwork.uploaded with `Prodigi did not reach the expected upload state.` Save permit started=false. The retained record cannot prove which browser event caused that original timeout.

The owner's reset at22:10:24UTC created generationb772ce30-3c2a-41a0-8a88-54cbef90983e. Its retry stopped22:12:13UTC at artwork.signin, before upload/Save permission or QA. The page-readiness timeout is labelled signin without proving a login redirect. The exact live order tab was signed in, on the intended order detail URL, with a leftover Image Editor showing GLOBAL-CFP-A3 and Excellent quality. No manual supplier edit, Save, upload or reset occurred during this diagnosis.

## Root defect

Reset authorisation contains the supplier's empty default-image placeholder (NotYetDownloaded,required=true,pageCount=0). `has_existing_artwork` correctly treats this as empty, so `replace_artwork` is absent. Full Reset also intentionally clears the prior product_browser receipt, so `selected_empty_product` is absent. The existing companion therefore receives neither signal that refreshes its owned stale tab before upload. The old editor/content connection may survive; the readiness timeout misleadingly reports signin. This proves a missing reset handoff branch, not the exact historical browser scheduling event.

## Local fix

For a live empty item with an explicit unchanged, unconsumed, generation-bound full Reset authorisation, issue the existing selected_empty_product flag. Require reset and exact-item worker capability. This reuses Companion1.7.45's existing fresh-tab path. Changed address/placeholder/generation or consumed authorisation blocks; ordinary empty items have no authority to clear an editor. Upload/Save/checksum/item/source/submission fences remain unchanged. No new permissions, companion version or countdown change.

Regression first failed for both an empty asset list and the exact placeholder shape, confirming reproduction. Validate expanded Python reset/product tests and39 browser tests before release. Production publication and guarded rerun await fresh owner approval under AGENTS.md; no live fix or rerun is claimed.


## Owner-authorised release and automatic recovery

Owner subsequently explicitly requested publication to Git/Render and recovery of SC3538 and the repaired Mike Tyson SC3533 item. Add one bounded recovery for the exact pre-Save readiness error only after an unchanged empty item, unconsumed Reset or verified product selection, fresh source/business and no submission are proved. Retire the unused upload token and retain generation/Save fences. Ordinary editor-preservation behaviour remains unchanged.

Tyson allocation967 successfully repaired its PSD and generated JPG, then failed product-readback after permitted Select. Read-only exact supplier DOM shows GLOBAL-CFP-A2/Black selected on Tyson with an empty Image Editor; the other two editions remain saved and Excellent. Add bounded readback-only recovery (never another Select click) and record only structural changed-field paths for the server comparison failure. Do not assume which supplier fields changed until that independent diagnostic is observed. Full QA and one shared order submission remain required; no sibling artwork is reset.


## Proven Tyson comparison blocker

The first live independent readback recorded only items[0/1].unitPrice.amount and lineTotal.amount changed: Prodigi repriced the two saved sibling items when the third product was selected. No artwork/address/variant/quantity path changed. Normalise only Money.amount for existing draft line prices during post-Select completion; retain currency and all other business fields. Pre-Select permit comparison stays fully strict. New policy supplier-price-readback-v1 supplies a bounded fresh readback-only budget after the fix; consumed Select permits remain intact. Independently require correct SKU/frame, no existing target artwork, no charges and unchanged source before admitting upload.
