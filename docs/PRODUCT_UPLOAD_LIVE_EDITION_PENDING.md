# Live publication before edition assignment

19 October 2026. PRODUCTS task 20261019-f7674113, owner
codex-live-edition-pending-20261019-01, isolated branch
codex/task/products-product-upload-live-publication-pending-ed-20261019-f7674113.
Started from current released main cb1a74b5 after Studio allocated its older
approved base. Other worktrees and unfinished changes were preserved.

Only exported Live prompt wording changes at runtime. Product/publication QA
still gates activation, channels, Markets and selected collection publications.
Pending edition metadata, assignment, PSD mapping or mirror and their expected
archived/disabled-cart effects do not alone block publication or trigger Draft
fallback. Edition readiness is reported separately; verified publication with
pending setup uses PRODUCT PUBLISHED LIVE — EDITION SETUP PENDING and the exact
operator MAP/assignment instruction. No readiness or purchasing success is claimed.

The prior Edition Ops success gate is replaced in place. Staging QA, activation,
storefront checks, final read-back, success reporting and fallback now agree.
Inherited pricing/QA Draft vetoes are explicitly scoped to staging in Live only.
Mode wording substitutions reverse before rebuilding saved prompts, preserving
idempotence and avoiding cross-mode residue. Saved commercial content, prices,
media, collection, tags and correlation/retry identity checks remain in force.

Draft and Update exported prompts were compared against the previous module and
are byte-for-byte unchanged. Existing edition ledger, allocation, counters,
storefront behaviour and purchasing protections are unchanged. No live-store
product was modified; the reported example ID is not included in runtime code.

Verification: 63 focused Python tests plus 11 subtests passed (modes, new Live
edition contracts, source/package and Edition Ops recovery), using synthetic
providers and disposable local PGlite. Node complete-prompt clipboard contracts
and topology validation passed. Chrome/Edge clipboard verification covers full
actual exported text, all three modes, pending-edition Live wording, current
manifest, correlation, save gating and no image/helper operations. Evidence is
local in output/product-upload-dropbox-prompt/.

These are prompt/clipboard contract checks, not an end-to-end execution by an
external assistant or a Shopify publication test. The user authorised Git and
Render release; deploy through the existing canonical sports-cave-os service.
No Blueprint sync, service creation or production product mutation is required.
