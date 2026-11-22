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
