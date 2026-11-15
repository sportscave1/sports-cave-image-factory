# V17 single catalogue and failure-reporting correction

Owner request: fix the apparent doubled editions and report why preparation is failing. This is a focused correction to the owner-authorised V17 go-live, based on `2964d5024194ab752eb2468ed1ef73e3313af849`.

Task `20261015-e07c46e5`, owner `codex/v17-single-catalogue-20261016`; isolated INTEGRATIONS branch `codex/task/integrations-fix-auto-editions-single-catalogue-present-20261015-e07c46e5`.

## Read-only production findings, 16 October 2026, 06:51–06:56 AEDT

- `edition_products`: 334 rows, 334 unique product identities.
- PSD mappings: 285 rows, 285 unique products and 285 unique Dropbox file IDs.
- Preparation queue: 285 rows, 285 unique products. No catalogue, mapping or queue duplication was found.
- `edition_orders`: 668 historical purchase/unit allocation records across 125 designs: 658 assigned Shopify, four assigned Etsy, two assigned eBay, three superseded Shopify and one cancelled Shopify. There are zero duplicate valid numbers within a product/run. These records are not the 334-product catalogue.
- Allocation-number fingerprint remains `f7238f595d4556d7b21ce037c6c643b1`, the same as before V17 activation. No production record was changed during diagnosis.
- The attached screenshot's six mutually exclusive mapped statuses total 285: 16 ready + 1 preparing + 110 queued + 45 review + 41 repair + 72 failed. Uploaded 61 and Remaining 269 overlap those statuses. Adding them again incorrectly counts the same artworks twice.
- At the later 06:51 checkpoint, queue states were 109 awaiting, 118 Blocked, 42 Needs PSD Repair and 16 Cloud Ready. The 118 Blocked included 45 pixel-verified artworks needing manual review; they are not all preparation failures. The queue continued draining during diagnosis; at a later read there were 105 eligible awaiting jobs, with no duplicate claims.

## Confirmed failures and limits

- 23 source files lack exactly one visible editable edition-number layer, 13 lack a uniquely recognised collector plaque, five cannot hold the complete edition range without changing formatting, plus other isolated repair conditions.
- 38 historical Blocked rows retain only `RuntimeError`, hiding the useful Photoshop cause. Fifteen generic failures have local retained journals from this V17 run. All fifteen retained inspections have `profile: null`, RGB/8-bit source, and no PNG output; staged copies were present. The exporter directly reads `colorProfileName`, which throws for an unreadable/untagged profile. This is a confirmed unsafe diagnostic path, not evidence that arbitrary profile assignment would be correct. The discarded historical exception text cannot be reconstructed conclusively for all 38 records.
- Other recorded failures include seven transfer timeouts, six reference-profile mismatches, four source/transfer value failures, four Photoshop inspection failures, four original/profile-evidence mismatches, three HTTP transfer failures and two oversized prepared packages. Counts are a point-in-time audit and overlap different historical/software revisions.
- The helper is connected and continues claiming catalogue work. It has not completed every artwork: valid jobs may finish, new artwork still requires review, and rejected source/layout/profile evidence needs individual repair. No production certification or successful new upload is inferred from a heartbeat or claim.

## Changes

- The existing Edition Ops table remains the single product list. Its preparation expander now loads a summary-only mode without a second product dropdown or duplicate Review/Retry/Prepare Now buttons. Existing row-status dialogs retain their actions and review controls.
- The compact summary explicitly shows `Catalogue: 334 (285 PSD mapped)`. Remaining/Uploaded stay in a tooltip marked as subsets; they are not presented alongside mutually exclusive status totals as more products.
- Summary rows and counts defensively count each product identity once. Catalogue identity count is added to the existing SQL aggregate, with no new database round trip or provider request. No mappings or allocations are rewritten/deduplicated.
- A source inspection explicitly reporting no readable profile now stops before expensive preparation with an actionable owner colour-review reason. No guessed ICC, source conversion, file rewrite or approval is introduced. The exporter also reports its unreadable-profile condition explicitly.
- Future preparation exceptions retain bounded, capability-redacted `failure-detail.json` locally. Public RuntimeError status no longer discards the fact that Photoshop failed or exposes local source paths/capabilities. Existing unknown-profile failures are not automatically retried or reclassified in production.
- The existing table density, search/filter/edit/scroll behavior, 25-second visible status polling, source ownership, queue/processor locks and approval requirements remain.

## Validation

Focused local regression: **45 passed, four optional PGlite-only skips**. Native SQL fixtures used a disposable loopback cluster in this task, port 56422. Tests verify separate catalogue/mapping counts, one row/count per identity even with repeated join results, unchanged allocation/mapping/approval fixtures, explicit profile rejection and capability-redacted local diagnostics.

**Six browser scenarios passed**, desktop 1280px/mobile 390px: summary-only mode has no visible second product selector/actions, count labels/tooltip explain subsets, 25-second batched polling remains, standalone review retains selection/confirmation/scroll, and existing manual visual approval works. Screenshots are under `output/single-catalogue/`. No live Photoshop preparation or approval was initiated for testing. Diff whitespace checks passed.

## File inventory and release scope

- `auto_editions_v17.py`
- `auto_editions_onboarding_api.py`
- `auto_editions_onboarding.py`
- `components/auto_editions/onboarding.html`
- `edition_version_ui.py`
- `scripts/studio/auto_editions_local.py`
- `scripts/photoshop/prepare_auto_editions.jsx`
- `tests/test_auto_editions_v17_ui.cjs`
- `tests/test_auto_editions_single_catalogue.py`
- `tests/test_auto_editions_single_catalogue_ui.cjs`
- `docs/AUTO_EDITIONS_SINGLE_CATALOGUE_FIX.md`

No schema migration, feature activation, new service, paid infrastructure, production database cleanup, approval or edition-number change is needed. Release through an isolated RELEASE worktree and existing three Render services. Update only the existing helper's `auto_editions_onboarding.py`, `scripts/studio/auto_editions_local.py` and Photoshop preparation JSX at an acknowledged idle close, retaining pairing/startup, source files, jobs and rollback copies. Unknown-profile PSDs require an owner-approved colour decision; ambiguous layout roles require individual review. Do not bulk retry old failures.
