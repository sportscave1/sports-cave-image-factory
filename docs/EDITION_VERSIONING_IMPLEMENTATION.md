# Edition Ops versioning and performance verification

Implemented 8 October 2026. No production editions, certificates, Shopify products or Render services were changed by this work. Nothing was deployed.

## Behaviour

- The existing `edition_runs` UUID is the release identity. An administrator supplies a distinct release label, start, limit, design revision reason and the expected current UUID. A request UUID makes repeated submissions idempotent.
- One database transaction locks the product using the allocator's advisory-lock key, archives the previous run as `expired`, snapshots its counters, creates a zero-sale `pending_sync` release and moves the product pointer. Allocations are blocked during the transition.
- Original allocations, source replay identities, certificates and customer/order associations are retained. The original run cannot accept new allocations. New certificates include the new release label and UUID; existing certificates are returned unchanged.
- A start of 5 produces zero sales. The existing allocator keeps its independent sales-counter invariant; the new release's UI/storefront reports 96 numbers available from 5 through 100. Reserved/skipped numbers are not fabricated sales.
- Forward corrections retain recorded sales. Rewinds below an issued boundary fail with Review Allocations / Start New Edition Version guidance. The separate administrator reconciliation action repairs derived cursor/baseline state without changing issued numbers or recorded sales.
- Ambiguous unversioned allocations/tombstones prevent a restart until an audited historical repair establishes their ownership. The implementation does not guess which design an old order belongs to.

## Shopify and recovery

`edition_versions.py` uses the existing Shopify client and metafield writer. A dedicated transaction advisory lease, compatible with transaction pooling, serializes mirrors against version transitions and allocations. Network work is outside interactive Streamlit execution. Business writes retain short transactions.

The same product ID and URL are retained. The code updates edition metafields and appends a necessary, escaped release disclosure to the freshly read product description. It does not submit variants, prices, images or unrelated metafields. The original description remains before the disclosure. The release marker prevents duplicate disclosures on retry.

Metafield writes use Shopify comparison digests and read-back verification. Database activation occurs only after disclosure and metafield confirmation. Errors and retry state persist on the run. Retries use the same release identity and desired values, with bounded exponential backoff (eight automatic failed attempts). Manual Retry remains available.

The existing order reconciliation worker resumes pending transitions and interrupted ordinary edits. No new service is required. Its current default interval is 900 seconds, minimum 300; the local two-thread dispatcher normally starts sync immediately. Configure/verify the existing worker rather than adding another service. Failure of release recovery does not prevent the worker's normal order reconciliation.

Orders predating the new release's confirmed activation fail closed for review. Existing fully allocated source units still replay their original allocation. Purchases during a pending transition may therefore require deliberate review of the correct design.

## UI and performance

The existing native data editor, product selector, data cache and Design Tracking are retained. Main changes:

- Compact neutral toolbar/buttons and 32-pixel table rows; shorter numeric headers and useful column widths.
- Fifty visible rows per page, while preserving the existing cached catalogue and product search.
- Number edits persist on the native editor's commit, not every keystroke. Backend confirmation precedes Saved; Shopify runs separately.
- Independent Streamlit fragments for the workspace table, Advanced controls, archive and sync status. Search, filters, pagination, dialog opening and archive opening do not rerun the app/sidebar.
- Expired editions query only when opened, with 25-record pages. Allocation detail is limited to 100 records (the maximum run size), audit detail to the latest 25 events.
- Background status refreshes preserve newer unsaved inputs and their optimistic concurrency baseline. Only the affected product is refreshed. Database polling is bounded to 90 seconds per operation; Refresh/Retry resumes checking if needed.

The native dialog's explicit Cancel/confirmed transition still uses a single app rerun to close and reconcile the workspace. Opening it, typing within its form, dismissing with Escape, ordinary number edits, search and archive interactions do not. Advanced full-catalogue reconciliation keeps its existing explicit refresh behaviour. These are not claims that every administrative mutation is rerun-free.

### Measured results

Local Windows Chrome, headless Playwright, identical synthetic 500-product fixture, three runs per version. Baseline Edition Ops source is commit `01bc526` (unchanged in subsequent `6527202`). No production APIs were used. Times include browser interaction overhead; search includes a separate instrumentation acknowledgement.

| Measurement | Before median (range) | After median (range) |
|---|---:|---:|
| Fresh browser context to table | 1,022 ms (1,011–1,050) | 503 ms (503–508) |
| Warm return from Home | 365 ms (271–379) | 280 ms (276–281) |
| Product search | 324 ms (318–333) | 273 ms (270–502) |
| Full app reruns per search | 1 | 0 |
| Additional catalogue loads per search | 0 | 0 |
| Rows sent to initial editor | 500 | 50 |
| Version dialog opening | Not available | 136 ms (133–143) |
| Archive visible after opening | Not available | 131 ms (121–133) |

An earlier paired sample showed essentially unchanged warm navigation (271 vs 279 ms); the small samples vary and do not establish a production latency guarantee. Existing cache reuse was preserved rather than claimed as a new query reduction.

At 4× CPU slowdown, 100 ms network latency and 200 KB/s download, a cold browser took 24.5 seconds to load Streamlit assets; warm return was 966 ms, search 826 ms and dialog opening 439 ms. Functional checks still passed without full-page search/archive reruns. Cold framework asset loading remains a limitation under throttling.

The final browser runs sampled 62 intermediate search frames: exactly one table remained mounted, with no oversized SVG icons. Screenshots and checks covered 1440, 1000, 750 and 390-pixel windows, dialog dismissal and repeated navigation. This fixture does not substitute for a full authenticated production-browser trace. Shopify sync duration, memory usage and long-session behaviour were not measured.

Read-only `EXPLAIN (ANALYZE, BUFFERS)` through the Supabase connector tested the old and new production read queries (limit 500, 331 products returned), without applying migrations or writing records. Three executions each: before 247.033 / 94.757 / 97.294 ms; after 68.695 / 66.448 / 66.180 ms. Median database execution improved from **97.294 to 66.448 ms**. Both remain one bulk query. The first baseline execution was an outlier; these small samples are not a load test. Local application credentials remain unconfigured, so this does not measure the full production browser/network path.

## Verification

- Existing Edition Ops, allocator, recovery, Shopify product and certificate suite: 205 tests, 203 passed / 2 previously skipped.
- Actual transition and hardening SQL in disposable PGlite PostgreSQL: 10 passed. Covers preserved history/certificates, zero-sale start, separate releases reusing a number, pending allocation blocking, immutable archive/audit, old-event rejection, idempotency, stale edits, forward corrections, reconciliation and failed-sync recovery.
- Shopify transport and worker recovery tests: 5 passed. No real HTTP mutations.
- Background-refresh edit-preservation tests: 2 passed.
- Total: **220 passed, 2 skipped**, plus browser checks.
- Python compilation, JavaScript syntax checks and `git diff --check` passed. This Streamlit repository has no separate Edition Ops production bundle/build target. A lint/type-check tool was not installed; compilation is not presented as a static type check.

PGlite tests execute the real migration/functions but use one serialized connection adapter. True simultaneous multi-connection Postgres execution and real Shopify confirmation remain staging checks; SQL locking and uniqueness are implemented, but those production conditions have not been simulated fully.

### Reproduce

1. Run `node tests/edition_postgres_server.mjs` (uses the repository's existing PGlite test dependency).
2. Set `EDITION_TEST_POSTGRES=1`; run `python -m unittest tests.test_edition_versions tests.test_edition_version_mirror tests.test_edition_version_ui`.
3. Run `streamlit run tests/fixtures/edition_workspace.py --server.port 8895`. Run `node tests/test_edition_workspace_ui.cjs` with Playwright available through `NODE_PATH`.
4. For comparison, launch the fixture with `EDITION_BASELINE=1` on port 8894 and set `EDITION_BASELINE=1` / `EDITION_URL=http://127.0.0.1:8894` for the browser script. `EDITION_SLOW=1` enables throttling.

Generated screenshots and logs are in the ignored `.tmp-edition-evidence/` directory.

## Migration and rollout

The initial transition migration already exists in commit `6527202`; it was not rewritten. Apply migrations through the normal workflow:

1. Existing edition runs, atomic ledger and independent-cursor migrations must already be installed.
2. `migrations/20261008041452_edition_version_transitions.sql`, if not already installed.
3. New additive `migrations/20261008045733_edition_version_guard_hardening.sql`.

The new migration replaces guard functions and adds deletion/null-input/transition protection. It does not reset any product, issue certificates or contact Shopify. The transition audit table is private with RLS; browser roles cannot execute the transition function. Administrator status is checked freshly in the database.

Deploy matching code to the existing app and supporting workers before allowing the first version transition. Verify the existing order reconciliation worker is enabled and Shopify has its existing product-write permissions. Do not downgrade to code that treats all releases as one product-wide ledger after a new version has been created. Preserve the additive schema/history and use a forward fix rather than destructive rollback.

The local application has no database credentials, but the Supabase connector enabled read-only inspection of the repository's documented authoritative project, `ceyzbfpuwuuxaiqwiltz`, on 8 October 2026. The transition function is not yet installed there.

| Product | Observed state | Diagnosis / action |
|---|---|---|
| Jack Brabham Pushing His Own Car | Next 50, sold 0, last assigned 0, no allocation rows, baseline 100 | Legacy baseline and stored sales contradict one another. Review the source evidence, then use audited reconciliation if the baseline is erroneous. Do not infer that this is a new design. |
| Sam Kerr Matilda's Wall Art | Next 5, sold/last assigned 94, baseline 93 plus one actual atomic allocation at 94 | A genuine unsafe rewind within the original release. Correcting that release requires at least 95; the requested revised artwork can instead be explicitly created as a new release starting at 5. |
| Shane Warne Tribute | Current run 1–24, next 25, sold 24; another run contains three non-live records at 91–93 | The original product-wide historical maximum mixes releases and incorrectly blocks 25. The new run-scoped read removes that false conflict without altering any allocation. |

No production correction or reset was performed. `python scripts/diagnose_edition_versions.py` also supports repeatable read-only diagnosis once local/database environment configuration is available. No schema or Shopify work is performed by that script. An allocation mismatch alone cannot establish whether a genuine artwork redesign was intended.

## Files

Application: `edition_ops.py`, `edition_version_ui.py`, `edition_versions.py`, `supabase_backend.py`, `shopify_sync.py`, `shopify_order_reconciliation_worker.py`.

Migration/tooling: `migrations/20261008045733_edition_version_guard_hardening.sql`, `scripts/diagnose_edition_versions.py`, this report.

New tests/fixtures: `tests/test_edition_versions.py`, `tests/test_edition_version_mirror.py`, `tests/test_edition_version_ui.py`, `tests/test_edition_workspace_ui.cjs`, `tests/edition_db_fixture.py`, `tests/edition_postgres_server.mjs`, `tests/fixtures/edition_base.sql`, `tests/fixtures/edition_workspace.py`.

Updated regressions: `tests/test_edition_ops_stability.py`, `tests/test_edition_ops_table_editing.py`, `tests/test_edition_ops_new_product_pull.py`, `tests/test_independent_edition_cursor.py`. The startup test now isolates the unrelated CRM worker; unsafe-rewind expectations were replaced by the required integrity-preserving behaviour and pagination/commit-save expectations reflect the new workflow.
