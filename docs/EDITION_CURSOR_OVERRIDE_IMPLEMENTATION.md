# Edition Ops explicit cursor override — 8 October 2026

## Cause and data path

Edition Ops could retain a next-number edit while its older save and mirror paths
rejected non-contiguous history or a cursor below the highest historical number.
The Shopify value consequently remained unchanged. Reconciliation could also
derive a higher cursor from historical allocations. Main-table pagination and the
legacy main-container padding selector were separate UI issues.

Read-only live verification: Sam Kerr Matilda's Wall Art is Shopify product
`gid://shopify/Product/8468358299955`, handle `sam-kerr-australian-matildas-art`.
Shopify currently returns next **95**, sold **94**, remaining **6**. Public HTML
contains `data-edition-next="95"`, padded `095`, and the corresponding claim.
No product values were changed during development.

The canonical product metafields are `sports_cave.edition_next_number`,
`edition_sold_count`, `edition_remaining`, and `edition_total`. The existing
atomic mirror also writes legacy `sports_cave.next_edition_number`, `sold_count`,
`remaining_count`, display text, and availability flags. Product owner IDs are
resolved by the existing backend. The repository's numbered-edition Liquid
snippet already reads the canonical next-number field and pads it to three digits.
No theme deployment or cosmetic number replacement is part of this fix.

## Implementation

- The native virtualized data editor receives the complete cached catalog;
  Previous/Next products controls are removed. Search selection, status filtering
  and native column sorting still operate on that catalog. Expired-history archive
  pagination remains independent. Shopify is not called while scrolling.
- Scoped main-container padding replaces the old spacing without negative margins.
  `Next Edition #` uses three-digit formatting; `Shopify Sync` is visible.
- Cell edits remain local until **Save & Sync Shopify**. Only changed cursors, or
  the explicitly selected conflicting row, enter the new override path. A reuse
  requires one confirmation. Other historical products are not reset implicitly.
- `override_edition_cursor` checks the active administrator, expected release and
  cursor, range and actual sales cap, then commits both product/run cursors and an
  immutable audit record. It never modifies historical orders or certificates.
- A UUID records the administrator's numbering authorization within the **same
  release**, not a new edition version. New allocations inherit that authorization.
  Number uniqueness remains enforced within each authorized numbering pass.
  Source/order/line/unit uniqueness and tombstones remain unchanged.
- Product advisory locks serialize overrides, normal allocation and Shopify
  mirroring. Stale edits fail rather than overwrite intervening orders. Database
  guards prevent reconciliation from replacing an authorized cursor. New releases
  clear the active override identity without removing its audit history.
- The existing background executor starts Shopify synchronization immediately.
  Compare-digest writes and readback verification are reused. Only verified writes
  become Synced. Failed writes retain the cursor and durable retry/backoff state;
  the existing order reconciliation worker resumes eligible retries after restart.
  Retry Shopify sync remains available for exhausted or corrected failures.
- Sold and remaining use actual stored sales counters. Starting at 005 does not
  manufacture four sales, and reusing 005 does not erase the prior purchaser.

## Migration and deployment

Apply `migrations/20261008065000_explicit_edition_cursor_override.sql` **after**
the atomic ledger, independent cursor, edition transitions and transition-guard
hardening migrations. It adds the private override audit table, nullable identity
columns, guards and an admin-only cursor function, and changes the run-number
unique index to include the authorized pass identity. It does not alter existing
edition numbers, sales or allocation records. The allocator patch fails closed if
the expected existing guard cannot be found.

1. Back up and rehearse the migration against a staging copy. Confirm the backend
   database login owns the objects or has the required private-table/function
   grants; never grant this function to `anon` or `authenticated`.
2. Apply the transactional migration during the normal maintenance window. The
   index change briefly locks the ledger; schedule appropriately for its size.
3. Deploy the same revision to the existing OS and order/webhook worker processes.
   No new service, plan, scheduler or theme is needed. Existing workers remain
   the recovery path; interactive saves use the immediate executor.
4. Verify an isolated staging product: override, actual readback, storefront,
   order replay, sales cap, restart and concurrent worker behavior.
5. An administrator may then explicitly save the desired live product number.

Do not drop the new uniqueness scope after authorized duplicates have been
allocated. Roll back UI exposure if necessary; retain the additive schema and
audit history and use a forward database repair. No automatic deployment occurred.

## Verification and measurements

Disposable PostgreSQL-compatible PGlite runs the real migrations/allocator; Shopify
transport is mocked. Tests cover 095→005, confirmation, admin permission, persistence,
same-release number reuse, preserved sales/certificates, unique order replay, cap,
stale edits, competing edits, release transitions, reconciliation guards, failed
sync/retry, read projection, compare-digest writes and required readback.

Streamlit AppTest verifies local edits, explicit save, reopening, and unaffected
rows. Chromium verifies all 500 rows in one virtualized grid, search with zero
extra loads/full-app reruns, archive isolation, responsive widths 390–1440, no
exceptions, and editing 005 followed by exactly one confirmed mock save.

Local fixture samples (not production latency guarantees): baseline initial
1,030 ms, warm return 255 ms, search 486 ms. Updated runs: initial 514–1,018 ms,
warm return 256–275 ms, search 246–486 ms. The final run measured 1,016 / 275 / 299 ms
(initial / warm return / search). There is no material warm-navigation
regression; these small samples do not establish a statistically significant
speedup. Both versions use zero additional catalog queries/full-app reruns for
search. The updated grid exposes 500 rows instead of a 50-row page.

All 61 focused regression tests, both Chromium scripts, Python compilation,
diff checks and Render topology validation pass. This Streamlit project
has no separate frontend production bundle/type-check command for these modules.
The local SQL adapter serializes transactions; real simultaneous PostgreSQL
connections, production Shopify writes/readback, storefront after a real write,
and production sync latency remain staging/rollout checks. Local Shopify credentials
were unavailable; the live metafield diagnosis used the read-only Shopify connector.

## Files

Runtime: `edition_ops.py`, `edition_version_ui.py`, `edition_versions.py`,
`edition_cursor_overrides.py`, `supabase_backend.py`, and the migration above.
Regression files: `tests/test_edition_cursor_overrides.py`,
`tests/test_edition_version_mirror.py`, `tests/test_edition_ops_table_editing.py`,
`tests/test_edition_ops_stability.py`, `tests/test_edition_override_ui.cjs`,
`tests/test_edition_workspace_ui.cjs`, `tests/edition_postgres_server.mjs`,
`tests/fixtures/edition_workspace.py`.
