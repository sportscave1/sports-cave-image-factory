# Durable Edition Ops + Orders PSD integration — local completion

Task 20261012-5849050d; owner codex-psd-01a12ffa.
Worktree: C:\Dev\SportsCaveWorktrees\sports-cave-integrations-dropbox-psd-links-edition-ops-orders-20261012-5849050d.
Branch: codex/task/integrations-dropbox-psd-links-edition-ops-orders-20261012-5849050d.
The category entry point and retained task were verified first. Both were clean;
the retained task HEAD was 1117a864da9684228b1345d16be1c6815485f2c4. No existing work
was discarded. New changes are local and uncommitted.

## Root causes resolved

Runtime mappings now come from Supabase/Postgres, never output/psd_directory.json.
Explicit local JSON paths remain solely for offline exports and fixtures. The
additive SQL proposal creates product_psd_mappings and product_psd_mapping_audit.
Stable product GIDs and unique Dropbox IDs enforce one assignment per product/file.
Manual attachment and backfill use transactions, serialized writes, optimistic
expected-file checks and audit records. RLS is enabled, client privileges revoked,
and server-only service-role privileges granted. No schema is created at startup.

Every page does one indexed audit revision query; mapping records are read in a
single batch only when that revision changes. Independent instances therefore
observe committed attachments on their next render, without TTL delays or polling.
If the database is unavailable the File column says Unavailable rather than falsely
claiming mappings are missing. Orders and Edition Ops share this exact source.

Edition Ops Status is now only Live, Offline or Expired. It uses enabled state,
confirmed edition-metafield sync evidence, current-run status, allocation limit,
next cursor and confirmed current-run sold count. Storefront publication and an
absent online_store_url have no bearing on the edition sync label. Existing errors
and retry states remain internal diagnostics. A current-run allocation count is
added to the existing read-only query, preventing sales/expiry from historical runs
from expiring an active replacement release. No allocation/metafield write changed.

The supplied claim that all 333 products were Synced is preserved, not overwritten.
Tests seed 333 synced local records and prove mappings/status projection leave all
333 records and their edition totals/cursors unchanged. Production sync state was
not independently re-read because this task authorizes local work only.

## Actual snapshot and backfill

The approved ZIP's three CSV hashes and identity crosschecks pass:
282 verified unique automatic candidates; 333 products; 51 unmatched; 40 review
files excluded; zero ambiguous matches. The offline empty-store preview proposes
282 inserts with zero conflicts/missing identities. Production may already contain
mappings; its own read-only preview is mandatory before execution.

Ignored output/psd_backfill_preview.json contains the complete offline preview;
output/psd_snapshot/unmatched_products_51.json contains unmatched identities.
Existing verified/manual rows are preserved. Conflicting file ownership or product
identity is reported and skipped. Execution requires explicit owner-approval evidence
and a matching, current database-preview hash. Changed previews roll back execution.

## Manual attachment and Orders

Missing Edition Ops files show a compact Add action in the existing File column.
It opens a same-origin modal picker inside Sports Cave OS, identifying the product,
listing/searching approved main-folder PSDs and showing available thumbnails for
selection. A filename mismatch requires explicit confirmation. Replacement requires
confirmation and records before/after audit state. Review folders are excluded.

Server routes recheck administrator/Files permission, same-origin POST, immutable
file identity and current main-folder location. Duplicate assignments and stale
selections are rejected. No PSD contents or filenames are changed. A successful
save sends a Streamlit component event to rerender the table without a browser
reload. Existing mappings can be replaced through the collapsed PSD links control.

Orders keeps its layout and PSD column position, resolves each product ID including
multi-artwork/historical lines, and uses new manual mappings on the next render.
Its genuinely missing mappings still show Not linked. Opening uses the existing
authenticated stable-ID endpoint and Dropbox's permission-protected preview URL.

## Changed files

Application: psd_mapping_store.py, psd_directory.py, edition_ops.py, orders_page.py,
files_upload_api.py, dropbox_integration.py, supabase_backend.py.
Picker: components/psd_picker/index.html and picker.html.
Activation: scripts/sql/product_psd_mapping.sql, scripts/backfill_psd_mappings.py,
and scripts/validate_psd_snapshot.py (explicit fixture storage only).
Tests: test_psd_durable.py, test_psd_picker_api.py, test_psd_picker_ui.cjs,
test_psd_links_ui.cjs, test_psd_directory.py, test_edition_ops_stability.py,
test_edition_ops_table_editing.py, test_orders_compact.py, and this report.

## Validation

169 Python tests passed, including real isolated PostgreSQL schema application,
idempotent 282-record backfill, multi-instance/reload persistence, transaction races,
manual priority, confirmed replacement audit, uniqueness, RLS denial, all 333 synced
fixture records, statuses and current-run expiry, existing save/reload/navigation,
Orders, Files API and edition-allocation/mirror regressions.

```
python -B -m unittest tests.test_psd_durable tests.test_psd_picker_api tests.test_psd_directory tests.test_psd_open tests.test_edition_ops_stability tests.test_edition_ops_table_editing tests.test_orders_compact tests.test_dropbox_integration tests.test_files_upload_api tests.test_edition_ops_allocation_integrity tests.test_edition_ops_catalogue tests.test_edition_version_ui tests.test_edition_version_mirror
```

Durable tests require PSD_LOCAL_TEST_PORT pointing to an isolated localhost
PostgreSQL database named psd_test with fake test credentials. They refuse a remote
host and never use the existing production connection configuration.

Browser tests passed: Add → Search → Select → mismatch Confirm → Save → Open PSD,
replacement confirmation, cancellation, unavailable/missing actions and no full
reload. All browser requests were intercepted fixtures, with no live network.
Run node tests/test_psd_links_ui.cjs with NODE_PATH set to the bundled runtime's
node_modules directory. No application dependency was added.

For 333 actual-snapshot rows, median local projection times over 20 runs:
Edition Ops 4.814 ms (previous 4.911 ms); Orders 1.319 ms (previous 1.367 ms).
The durable revision/cached-read round trip adds 9.939 ms locally; cold reads also
fetch the mapping batch. There are zero per-row Dropbox calls. These are local
processing/database timings, not production page-load measurements.
Evidence: ignored output/psd_durable_performance.json. Static Studio verification
and diff whitespace checks passed. Temporary PostgreSQL used a localhost-only
Docker container with fake credentials and no repository/customer-data mounts.

## Production activation — separate approvals required

None of these steps was executed against production.

1. Owner reviews and explicitly authorizes applying
   scripts/sql/product_psd_mapping.sql in the existing Supabase project's SQL
   editor/approved migration process. The existing server DB role must retain its
   privileged server-only access; no browser client policies/keys are introduced.
2. In the approved server environment, with existing credentials kept server-side,
   run a read-only authoritative preview:

```
python -B scripts/backfill_psd_mappings.py "C:\Users\hello\Downloads\Sports_Cave_Codex_PSD_Snapshot_2026-10-12.zip" --database-preview --output output/psd_database_preview.json
```

3. Review proposed inserts, preserved mappings, conflicts and missing products.
   Obtain separate owner approval for that exact backfill, then execute:

```
python -B scripts/backfill_psd_mappings.py "C:\Users\hello\Downloads\Sports_Cave_Codex_PSD_Snapshot_2026-10-12.zip" --execute --owner-approval "OWNER / approval evidence" --reviewed-preview output/psd_database_preview.json --output output/psd_backfill_result.json
```

4. Separately authorize the normal reviewed release/commit/push/deployment process
   for this tested code to the existing canonical sports-cave-os service. Never
   create another primary service. Apply schema/backfill before activating the new
   readers so the directory is populated on first load.
5. Verify authoritative mapping counts, 51 missing records, preserved edition-sync
   evidence, authorized Dropbox preview opening and permitted manual attachment in
   the activated environment. Production latency and Dropbox scopes/preview URLs
   require that future authorized validation. No full Sports Cave OS preview/server
   was started in this local task.

No commits, pushes, deployments, production migrations/backfills, production
credentials, or live Shopify/Dropbox modifications were used. Exported files remain
ignored. Local Studio status: Tested; production activation remains pending.
