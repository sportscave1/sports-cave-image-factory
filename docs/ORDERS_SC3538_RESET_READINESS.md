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


## Live results and companion1.7.46

SC3538's guarded recovery uploaded and independently verified its JPG at23:10:30UTC. Its QA pass then stopped before the shipping/tax permit with the generic Interrupted QA receipt. Code review proves the companion catch path discarded all actual QA transport/readiness exceptions in favour of that generic message. This record does not prove a worker reload or an actual logout.

1.7.46 preserves the original QA connection error and stage, labels artwork readiness honestly, and wakes the exact worker-owned tab once after repeated responsive Loading/missing-receiver probes (the existing wake handled only a hanging response). Ownership/URL checks and new-document fences remain; no user tab/global browser setting changes. Test both previously missed readiness behaviours and diagnostic preservation. A separate advertised Page-Ready capability is required for bounded pre-permit interrupted/open-stage QA recovery; source/business/shipping and saved JPG checks remain mandatory. No artwork Save or Select permit is replayed.

Tyson's readback after the price fix independently verified the canonical product. Upload then continued; the two saved sibling JPGs and their item QA receipts were retained. Final order-wide QA/submission still must be observed for all three.


Tyson subsequently hit the same pre-Save signin/readiness fallback under1.7.45, even after one old-policy retry; no Save permit was committed. The Page-Ready capability in1.7.46 is also required for a single fresh owned-page-ready-v1 recovery budget. Existing source/business/empty-slot/generation checks remain, and that fixed-policy exhausted retry stays blocked. This prevents older companions repeatedly consuming readiness attempts and does not reset any saved sibling artwork.


## Fresh context fallback,1.7.47

1.7.46's bounded wake did not make the retained SC3538 QA tab ready. Its accurate failure remained QA open, before any permit; saved artwork intact. Read-only browser comparison: binding the old tab timed out, while a newly opened tab at the exact same order URL loaded with document.readyState=complete and the exact main h1. Close that diagnostic tab without supplier edits. This demonstrates a usable fresh context, without proving the exact browser-internal cause of the old context failure.

1.7.47 adds one fresh owned-tab fallback only for an already-authorised fresh QA/product or explicit empty/replacement upload handoff. Recheck the old tab's ownership/URL, preserve it, create exactly one active tab at the pinned URL, retarget the in-memory transfer, and require actual page readiness again. Ordinary editor-preservation flow has no fallback authority; a new failed tab cannot recurse/create a tab loop. No new browser permissions.

The fresh-context capability gates a policy-specific recovery budget. A pre-Save active handoff may also be retired only after five minutes, matching token-scoped progress stale for90seconds, unchanged empty assets/full business/source and a verified product or unconsumed exact Reset. Revoking that unused token prevents a late Save permit; already-used Save permits and changed assets stay blocked. Successful original JPG receipts/sibling QA remain untouched.


## Observed fresh-context acceptance and supplier429

With1.7.47 active, SC3538 passed all QA at23:39:42UTC and submission was independently confirmed on_hold23:40:20UTC; original JPG receipt retained. Tyson then cleared readiness and upload processing, but a server GET returnedHTTP429 at artwork.permit before a Save permit was committed. This is an observed supplier rate-limit response, separate from the earlier sibling-price comparison and retained-context issues.

Limit concurrent GETs to two per process; retry only GET429 up to three times with numeric/HTTP-date Retry-After (or bounded backoff). Never retry writes. Long supplier cooldowns defer rather than retry early; record retry time for an unused pre-Save429 and allow one guarded recovery only after independently proving the same empty assets/source/full business and no used Save/submission. Exact current stage readiness is also added to the receipt API allowlist: recent client diagnostic rename omitted that server contract, which could strand an otherwise stopped unused handoff. Test the actual Starlette receipt endpoint, not only separate module mocks. Server-only follow-up: Companion1.7.47 unchanged.
