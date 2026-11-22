# SC3537 product selection investigation

23 November 2026 (Australia/Sydney). Companion 1.7.42. After reviewing the tested candidate, the owner explicitly approved publishing, installing and the guarded SC3537 rerun. Runtime activation and successful live submission remain separate acceptance checks.

## Evidence

SC3536/allocation970 and SC3537/allocation971 have identical original mappings: Black / XL, GLOBAL-CFP-A1, Black frame. Both imported items initially needed product selection. SC3536 independently verified that selection and later passed upload/QA and submitted. Do not Reset it.

SC3537 received its Select permit at 2026-11-22T18:40:58Z. The permit route returned HTTP200. Its finish receipt stopped at product-select, before the program advanced to product-readback, and independent supplier readback still found no selected SKU. Thus the failure precedes artwork upload and final QA; it is not an XL SKU mapping difference.

The previous server deliberately omitted the product client's error from finish(), losing the immediate browser cause. The exact original DOM exception cannot now be recovered from the stored receipt. Do not claim that a particular React replacement was conclusively observed on this order. Code review found and tests reproduce a readiness gap: after waiting for a server permit, the catalogue was resolved once and clicked without waiting for a replaced/disabled card or restoring the intended colour after rerender.

## Correction

Use a bounded, exact-SKU/colour readiness helper both before and after permission. Re-resolve React's current controls, restore only the authorised catalogue colour, wait for it to persist and Select to become enabled, then click once. Identity failures abort immediately. Preserve one permit and never replay an uncertain supplier write. The same helper covers normal blank items and Add product during consolidation.

Preserve the bounded product client stage/error through the paired finish endpoint and display it beside independent supplier verification failure. A client error never overrides actual saved supplier truth or makes a check pass.

For the existing old failure, explicit owner Reset can retire the expired pre-click handoff only after independently proving the original exact item is still blank, unpaid, without artwork, and unchanged in business/source identity. It requires the old product-select failure, expired 15-minute permit and no browser/write/submission intent. Ordinary polling/readback does not repeat Select. Wrong/changed items, recent permits and post-click uncertainty remain blocked. The 15-minute permit expiry is unrelated to Prodigi's production countdown.

## Validation and release status

73 distinct focused Python checks passed across the combined 72-case suite and the additional full-Reset integration case. All 95 companion/UI checks passed. Includes all 16 original mappings, delayed/replaced catalogue controls, colour restoration, exact-item targeting, error forwarding, expired-blank owner Reset, rejection of changed/young/post-click handoffs, supplier write fences, submission/Reset guards and package contents. Only synthetic fixtures/disposable local database were used. Render topology validator and diff checks passed.

No live Reset, Select, upload or submission was made during development. Release authorization has now been granted under AGENTS.md: publish the focused candidate, verify Render and package, activate 1.7.42, request guarded Reset for allocation971 and observe exact variant → numbered JPG → QA → one submission. Keep SC3536 and Prodigi's countdown unchanged. Do not claim that the original discarded DOM error has been recovered or that all supplier failures are eliminated.

## Live rerun and 1.7.43 follow-up

1.7.42 was activated and server 3ed444d4 reached live. Owner Reset returned HTTP200 and created a new reset generation. The rerun stopped before any new Select permit: the exact old worker-owned order tab never reported ready. Edge showed that tab Sleeping. The newly preserved client error exposed this separate readiness failure; it was not a new SKU/frame mismatch.

Product selection previously reused its saved tab without the fresh-page step already used by QA. Reloading an unpacked extension invalidates receivers on existing pages. 1.7.43 now reloads only its own pinned tab before product selection and before explicitly authorised artwork replacement. It retains the new-page-instance fence and canonical URL handling. Ordinary artwork handoffs still do not reload unexpected editors. The readiness error now describes loading/sign-in state rather than asserting the user must sign in.

97 companion/UI checks and offline package verification passed, including immediate missing-receiver recovery on an old owned product tab and full-Reset refresh before replacement upload. The server's 73 focused Python checks remain unchanged. This follow-up is within the explicitly authorised publish-and-rerun work. Successful final SC3537 submission remains to be observed; no paid order or countdown preference was changed.

## QA permission transport recovery

With 1.7.43 active, the fresh-tab rerun automatically selected and independently verified GLOBAL-CFP-A1/Black, transferred and saved the numbered JPG, and independently verified its full-image fit. No manual supplier-tab wake or supplier editing was needed. Full QA then encountered HTTP503 at /qa/permit, not a supplier shipping validation response. The client represented all rejected permit requests as a draft/quote change. The receipt's started=false proves no shipping/tax permit was committed. The original 503 exception class was not logged, so do not claim a specific database exception was established retrospectively.

Separate the short authentication slots for critical browser/QA actions from ordinary polling, preserving bounded concurrency and per-request paired authentication. Log QA request stage, exception class and SQL state without raw customer/provider data. Do not replay permits or supplier writes.

Bounded server recovery may retire this known pre-permit QA failure only when started=false, artwork is already independently verified, source and pinned business still match, shipping service is unchanged, and no submission exists. It requeues a fresh QA handoff, preserving artwork and requiring a new guarded permit. Changed address/assets/shipping, used permits and exhausted retries stay in review. Cap recovery at two attempts. No extension reload is needed for this server-only follow-up.

## Saved inserts summary, 1.7.44

The QA-only retry then timed out opening/loading the inserts control, still before a shipping/tax permit. Read-only inspection of the actual order showed the correct two saved inserts: Round packaging sticker and Packing slip (colour). The dialog was inspected and cancelled without saving or assigning anything. This establishes presence, not the precise browser event that prevented the background dialog from becoming ready.

1.7.44 reads the unique Inserts card's saved count and names first. It accepts arbitrary names under the owner's presence-only policy, requires an unambiguous count/name match, and records them without opening/editing the dialog. Missing, empty or ambiguous summary falls back to the existing bounded dialog read; no phantom insert is created or passed. The known unstarted inserts-loading failure uses the same two-attempt recovery cap and unchanged source/business/shipping/artwork checks, retaining the verified image.

Validation: the full companion/UI set passed 103 checks, plus a further full-QA integration case proving no insert-dialog clicks and no readiness delay when the saved summary is present (104 distinct Node checks). Thirteen focused Python checks passed, covering both shipping-transport and inserts-loading recovery plus package contents. Genuine empty inserts, changed data and already-used permits remain blocked. This continuation is within the owner's authorised publish-and-rerun work; final submission must still be observed.
