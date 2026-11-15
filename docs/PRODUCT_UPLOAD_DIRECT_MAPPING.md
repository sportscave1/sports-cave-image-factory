# Product Uploads direct mapping finalisation

## Scope and cause

Verified PRODUCTS category checkout: `C:/Dev/SportsCaveWorktrees/sports-cave-products`, branch `codex/category/products`, clean before work. Per repository task-isolation rules, implementation is in `C:/Dev/SportsCaveWorktrees/sports-cave-products-product-uploads-direct-mapping-finalisatio-20261020-86b78075`, branch `codex/task/products-product-uploads-direct-mapping-finalisatio-20261020-86b78075`, owner `codex-map-finalise-20261020`. It was clean and fast-forwarded to main 6e8fe31b before editing. Other worktrees were not edited.

The mapping handler called `self.onboard(pid)` after successful product lookup. That helper can enqueue and wait for shared onboarding even though webhook registration is independently responsible for the OS record. This confirmed execution dependency is removed. The exact production exception was not retrieved, so its underlying queue failure is not claimed as diagnosed.

## Change

Only the mapping handler and mapping component change runtime behaviour. Find product is untouched. Shared sync/onboarding and webhooks are untouched. UI has Finding product followed by Linking PSD. Missing Shopify products can retry lookup without typing an ID; ambiguous candidates still require confirmation. Missing Edition Ops records show a waiting state and never initiate sync or move a PSD.

Finalisation reads the existing Edition Ops product/run by exact Shopify identity, retains its consistency checks, acquires the existing preparation hold and executes the existing move, attach and verification transactions. No edition numbers, allocations, counters or runs are created or changed by this flow.

The existing move relocates the captured PSD file from Review into the configured Live directory; it does not move the parent folder. This implementation is retained. Review-source filenames now use the Edition Ops displayed `product_title`, rather than the potentially different Shopify title. The existing sanitiser handles Windows-invalid characters, reserved device names and the .psd extension. `edition_name` is the run label (e.g. Numbered Edition), not the displayed product name. Existing Live/prepared mappings are preserved.

Durable move intents and stable Dropbox file ID/content identity reconcile lost responses. Conflicting destinations are rejected without overwrite. Attach/link failures remain incomplete; retries resume without repeating a completed move. Success follows fresh destination, mapping and active-run verification and the existing transactional readiness/queue admission. Unexpected service failures name the incomplete stage.

## Local verification

`tests/test_product_upload_mapping.py` uses real disposable PGlite PostgreSQL with simulated Dropbox and Shopify providers. Its setup now models completed webhook registration before MAP, rather than expecting MAP to enqueue registration. Tests cover direct finalisation, missing record then webhook arrival, missing product then lookup retry, exact identities, safe repeated completion, move response loss, move/link/commit failure, conflicts, stale leases, concurrent calls, preserved counters, retained prepared mappings, and sanitised Edition Ops naming.

`node tests/test_product_upload_mapping.cjs` covers two UI steps, no requests on mount, explicit lookup retry without a typed ID, ambiguity confirmation, duplicate clicks, polling lifecycle, stale responses and failure states. Render topology validation and Studio verification also run.

No live Shopify writes, production record mutations or real Review/Live file operations are performed in testing. Deployment status and exact test totals are reported in the task response. A production user mapping is not claimed as exercised.
