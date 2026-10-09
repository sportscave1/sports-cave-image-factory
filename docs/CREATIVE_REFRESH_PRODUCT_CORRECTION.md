# Creative Refresh product correction — local verification

## Root cause

`ads_page.render_product_name_input()` returned early when the Meta Review handoff contained a canonical product mapping. It rendered a static caption instead of the existing searchable selector, and reapplied the imported title on every rerun. Carousel validation correctly compared against `source_winner.product_mapping`, but the operator could only change the URL, leaving that mapping stale.

The old selection callback also called `meta_review_handoff.confirm_selected_product()`, which writes shared Meta Review mappings. The corrected Creative Refresh callback uses a draft-local helper instead; shared confirmation functionality remains untouched elsewhere.

## Changes

- The existing compact, searchable product selector remains visible for imported products. Import still supplies its initial value. Exact manually entered names resolve through the existing canonical catalogue helpers; an arbitrary label does not establish a new product identity.
- Explicit selection updates a copied current source mapping, product ID, handle, title, record key and canonical row. Winning copy, image references, source ad identity and country/category controls remain intact.
- Verified catalogue URLs populate automatically. UTM parameters and supported click IDs carry across products; an old product's variant or fragment does not. A URL already pointing to the selected product retains its parameters and fragment. Subsequent URL edits remain supported.
- **Use product from URL** resolves a trusted storefront URL against the already-loaded catalogue and applies that product through the same callback. Unknown, unsupported-host or ambiguous URLs do not guess a product or create records.
- Validation uses the corrected working mapping. The mismatch message identifies the selector/URL correction action. The same selector correction supports Carousel, Instant Experience and shared single-image refresh forms.
- Correction provenance contains the source ad/decision identity, original mapping and selected mapping. It travels in the existing refresh context and saved-workspace/package contracts. No historical Meta Review mapping, Shopify product, other ad or existing generated result is rewritten. Normal Submit builds the corrected result through the existing workflow.

## Files changed during this task

Application: `ads_page.py`, `ads_refresh_generation.py`, new `ads_refresh_product.py`.

Tests: new `tests/test_ads_refresh_product.py`, `tests/test_ads_refresh_save_restore.py`, `tests/test_meta_review_products.py`.

Report: `docs/CREATIVE_REFRESH_PRODUCT_CORRECTION.md`.

## Verification

**139 focused tests passed in 17.979 seconds**, covering:

- Normal imported product preselection with no confirmation action.
- Peter Brock → Greg Murphy identity/URL correction.
- URL-first selection, exact manual name resolution, tracking parameters and malformed URL recovery.
- Genuine mismatch rejection and unsupported URL handling.
- Isolation from another ad in the same campaign and original source history.
- Streamlit selector callbacks, URL-first callback and reruns.
- Corrected Carousel and Instant Experience result/prompt generation.
- Saved workspace round-trip and mocked saved packages entering the existing Posting form with Greg Murphy's product ID and URL.
- Existing refresh plans, creative references, winner copy, image save/handoff and IE realism behavior.

Command:

```text
python -m unittest tests.test_ads_refresh_product tests.test_ads_refresh_save_restore tests.test_ads_refresh_generation tests.test_ads_refresh_workflow tests.test_ads_refresh_plan tests.test_ads_refresh_reference tests.test_ads_posting_handoff tests.test_meta_review_products tests.test_ads_ie_refresh_realism_priority
```

The broader `test_ads_creative_refresh` run also exposed two existing source-text assertions against unchanged files: sidebar selectors in `app.py`, and the old clipboard implementation literal in `ui_components/prompt_copy/index.html`. Neither expected literal exists in HEAD. These unrelated implementation-string assertions were not changed. The old test expecting a shared mapping write was updated to assert draft-only correction, as required here.

`git diff --check` passed. Tests used synthetic product records, Streamlit's local harness and mocked saves. No live Meta posting, Shopify product modification or remote save was performed by this task. No new tables, dependencies or API queries were introduced. URL resolution requires an unambiguous product in the existing loaded catalogue; unavailable products are not fabricated.

## Repository activity note

The task began at HEAD `44a13e1`. During implementation, an external action advanced HEAD to `bbc13e3` (`Deploy CRM personalisation and Shopify recovery discount integration`) and included some in-progress product-selector edits. This agent did not issue a commit, push or deployment command, and did not reset or revert that external change. Consequently, the current uncommitted diff contains only the subsequent refinements/tests/report, rather than every file changed during this task. A commit message alone does not establish whether a deployment occurred.
