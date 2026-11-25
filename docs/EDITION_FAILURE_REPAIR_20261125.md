# Edition failure repair — 25 November 2026

Task: 20261125-caab8a85. Owner: codex-edition-recovery-20261125-4d6d8fc4.

## Observed failures

- SC3557, allocation 992, edition 002/100, existing Prodigi order 75429608215403520: "Customer shipping details differ from the saved Shopify order. QA has unresolved checks or supplier issues." All other displayed preparation checks passed. Read-only comparison of Shopify and Prodigi confirmed the Shopify company was copied into Prodigi address line 2, with the Shopify apartment/address2 field empty. `shopify_recipient` omitted company, so the full-address check rejected otherwise matching details.
- SC3559, allocation 994, edition 081/100, existing Prodigi order 75438703223258112: "Product selection: No Prodigi product is selected on this item. Select the existing Fulfilment reference GLOBAL-CFP-A1 and matching frame before preparing artwork. Companion: The worker order tab changed before wake-up." Prodigi confirmed the item had no product. The historical tab URL and ownership map were not captured, so the precise event that triggered the fence cannot be established from this message alone.

## Changes

- Preserve Shopify company as supplier line 2 only when address2 is empty. Explicit apartment/unit data and strict comparison of name, street, city, state, postal code and country remain enforced.
- Before any supplier action, an authorised product/reset plan can recover once into a fresh tab for the same pinned supplier order if the old owned tab has changed. Preserve the old tab. Changed ownership and sign-in requirements remain blocking. Unsaved ordinary artwork cannot use this recovery. Re-read the tab map after tab creation to preserve unrelated entries and reject ownership races.
- A permitted shipping change may cause Prodigi to recalculate monetary amounts and shipping quotes. Admit one fresh QA/quote permit only when every non-price business field and every currency still matches. Retire the previous token; retain the saved artwork; never mark the repriced order approved from old evidence. Further changes still block.
- Companion package version 1.7.58. No permission or host-access expansion.
- Update the stale login-isolation test to assert the existing exact Prodigi login route and its single sign-in script. No runtime login permissions changed.

## Verification

- `python -B -m pytest tests/test_prodigi_preparation.py tests/test_prodigi_qa.py tests/test_orders_release_package.py tests/test_edition_failure_recipient.py -q`: 66 passed, zero skipped using disposable local PGlite. Network is forbidden by the preparation test fixture.
- `node --test tests/test_prodigi_browser.cjs`: 55 passed.
- `node --test tests/test_edition_failure_tab.cjs`: 7 passed.
- Python AST and JavaScript syntax checks passed.
- Additional dashboard QA regression suite: 62 passed with disposable PGlite. Combined existing/new browser tests: 63 passed.
- Broader release checks completed: 587 Orders Python tests and 33 subtests; 223 browser checks; topology passed. The corrected browser guard preserves destination-change rejection for QA documents. Email first failed because global Python lacked pglast/IMAPClient; using the already-installed project packages plus disposable PGlite passed all 341 tests and 17 subtests with zero skips. Original failed/skipped attempts are retained, not relabelled as passes.

## Live recovery and remaining work

The user explicitly requested requeuing these two existing orders. SC3559 Reset was requested through the existing Orders UI. It then verified the original product/frame and advanced to artwork upload and supplier image processing. It then stopped at "Product, artwork, address or inserts changed during QA." The pinned item price was USD 64.22; the saved supplier dashboard showed USD 64.27 after Express was selected. This was included in the repricing recovery fix. Exact current API-field differences were not captured, so any remaining non-price mismatch must still block a fresh pass. No duplicate supplier order, payment or Submit action was performed.

SC3557 remains blocked by the server mapper until the fix is released and its snapshot is refreshed through the existing reset flow. Do not remove the real company from either source or supplier address to force QA to pass.

The user explicitly authorised committing, releasing these fixes, updating the installed companion and finishing both existing orders, and confirmed Nathan's Render workspace. The two changed extension files were backed up and installed locally; an unrelated installed composer change was preserved. The user confirmed the first Edge reload; one final reload is needed for the browser guard correction because browser policy blocks internal extension-page automation. Final checks passed. Server release and live order recovery are the next operational steps. After release, requeue the same allocation, verify both exact existing supplier orders, edition numbers, frame/size, shipping service, artwork, inserts and final QA; never describe a pending job as passed. These fixes address the observed cases, not a guarantee against every future supplier or network failure.
