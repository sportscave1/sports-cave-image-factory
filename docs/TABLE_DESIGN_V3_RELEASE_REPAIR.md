# Table Design V3 final release repair

Base: GitHub main `aa40acf66c7dcf7db7159fb1485f5bdc3265bbeb` (fetched 10 October 2026). No application logic, API, database schema, Render service identity or routing was changed by this release repair.

Main advanced during validation from `3e3c6df` to `aa40acf` (navigation V4). A fresh remote clone received the cleanly applying table diff. The only intervening files are top-bar HTML, sidebar theme and their two tests; none are replaced by the table release. Baseline CRM/legacy evidence was captured at `3e3c6df`; all involved code and tests are identical at `aa40acf`. The exact-package gate also runs the updated navigation tests.

## Conflict resolution and preservation

The old Meta import hunk predated the deployed `deepcopy` import and reliability/performance changes. Reconstructed only the shared density import and four missing row-height arguments from current main. The early temporary campaign table retains its existing 32 px density; stale-cache handling, retry/overview behaviour and all metrics remain current.

The old CRM hunk targeted a Flow Settings editor already removed from main. Dropped that obsolete hunk completely. Only the remaining history dataframe gets shared density. No removed frontend or old email editor is restored.

Other original styling hunks applied cleanly. Audited 148 native rendering calls in 28 modules, including nine Meta calls and one CRM flow-history call. All existing 28/30/32/48 px exceptions remain. Full Python AST equality excluding the density import/arguments was checked for 26 table modules; app.py and os_pages.py additionally contain the intended shared CSS injection/removal. Four component JavaScript bodies remain unchanged. Shared CSS, 34 px default density, scoped HTML skins and the original design system are preserved.

All application integration edits were made in a fresh remote clone. The original workspace's unrelated application changes and untracked files were not copied into the release or overwritten.

## CRM timing investigation

Both original failing tests reproduced on clean main: the 10-second completion deadline and the four-second independent-completion assertion. Selecting installed Chrome instead of absent bundled Chromium made thumbnail rendering work and the 10-second test pass, but the four-second test still failed. These results establish a baseline issue; they do not prove every timing delay is caused solely by the browser installation.

Main already provides `tests/fixtures/crm_safety_without_thumbnail_workers.py`, documenting that asynchronous thumbnail prewarming pollutes SQL counters and timing benchmarks. It mocks optional prewarming at the suite boundary, while running all existing email safety tests with their original assertions and deadlines.

Using that unchanged fixture with disposable local PostgreSQL: **395/395 passed on baseline and 395/395 passed on integration**, including both deadline tests. Four thumbnail storage SQL tests passed separately, and thumbnail cache tests also passed. The final release gate runs the safety fixture plus storage tests together (399 tests). No failing test was edited, disabled, marked skipped, or given a longer deadline. Thumbnail rendering is validated separately from delivery/concurrency safety.

## Other baseline diagnostics

`test_orders_loading_ui`: the same seven failures occur on baseline and integration (137 tests): five legacy Edition Ops render/save expectations, one old mockup helper expectation and one old product-upload copy expectation.

`test_edition_ops_new_product_pull`: the same catalogue-size expectation fails on baseline and integration (17 tests): expected 50 rows, received 120.

`test_ads_creative_refresh`: one sidebar-source assertion now fails on clean current `aa40acf` and the exact package: expected 41 px indentation, while navigation V4 deliberately uses 36 px. Both runs execute 61 tests with the same one failure. The 27 updated sidebar/top-bar tests pass. No navigation styling is reverted.

These nine existing failures are kept visible in the gate. Their exact identities, assertion messages, test counts and failure summaries must match `tests/fixtures/table_v3_known_baseline_failures.json`; any additional or changed failure blocks publishing. Current Orders compact/reader/deduplication, Edition Ops editing/stability/recovery/catalogue/allocation and Design Tracking behaviour tests remain mandatory passes. We did not restore obsolete UI merely to satisfy legacy tests.

## Verification and limitations

Integration unit results are in `table-v3-evidence/release-validation.json`. Meta Review: 235 tests; Creative Refresh: 61 (60 pass; one current-main navigation assertion above); Posting handoff: 15, with additional Meta posting/carousel/import suites; Design Tracking: 21. Current CRM Flow Settings-removal and editor tests pass. Generated skins and canonical Render topology are checked. No Blueprint sync occurs.

The release gate runs Chrome and Edge table checks (50–1000-row fixtures, sorting/filtering/scrolling, selection, native editing, local autosave, real Orders fixture and custom components), Chrome/Edge Meta desktop/narrow/search/refresh/outage checks, and real CRM checkout operations/live browser fixtures. These are synthetic/local checks, not production customer-data or live Meta performance measurements.

A ready package has manifest schema 2, status `verified`, and a verification receipt from running the exact deployment script with `-VerifyOnly`. The receipt lives outside the frozen patch to avoid changing the candidate after verification. The candidate itself cannot publish. No commit, push or deployment is performed during verification.

## Safe manual release

`deploy_table_design_v3.ps1` rejects old manifest formats and verifies its own hash, patch hash, asset hashes, output hashes, exact file allowlist and frozen Git tree. It clones GitHub main afresh, requires the verified base revision, checks/applies the patch, and runs the full release gate. It re-fetches main before publishing. If main moved, any check fails, or the index changes, it stops. Normal fast-forward push is used; no force push, merge or conflict override is allowed.

The original workspace index and worktree are never staged, reset or stashed. Tests may regenerate screenshots in the isolated checkout; only the previously frozen, validated index can be committed. The existing Render auto-deployment is triggered by the user's normal push to main; no new service is created.
