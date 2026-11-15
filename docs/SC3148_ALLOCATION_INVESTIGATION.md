# SC3148 — production allocation repair

## Root cause

The installed `allocate_edition_line_units_atomic` RPC from
`20260828_fix_sparse_legacy_allocator.sql` required next=sold+1 and
last_assigned=sold. Edition Ops correctly permits an independent manual cursor.
The old RPC rejected the valid next=50/sold=0 state before entering its quantity
loop. This was not a race between two purchased variants: Shopify has one Black/L
line with quantity two. Numeric/GID ingestion aliases represented the same line.

Render first recorded the failed allocation on 11 September 2026 at 23:53 UTC;
reconciliation repeated the same error. The local PostgreSQL regression harness
reproduces that exact old-RPC failure and validates the replacement.

## Authoritative evidence before repair

- Product 657, `gid://shopify/Product/10431944393011`.
- Handle `the-first-shift-willie-o-ree-wall-art`.
- Active run `9799b113-0ff2-4dd6-9185-381357d04748`, Original Edition, total 100.
- Product/run next 50; sold 0; remaining 100; active, not sold out.
- Adjustment `c50e76f5-e622-412b-ba24-b63e4e59c647`: manual_app / Edition Ops save,
  next 1 to 50 on 6 September 2026 at 23:43:22 UTC. Sales stayed independent.
- No product allocations, tombstones/reservations or certificates. 50/51 were unused.
- Order `gid://shopify/Order/7408832905523`, #SC3148: PAID, not cancelled.
- Line `gid://shopify/LineItem/17545899573555`, quantity/currentQuantity 2.
- Variant `gid://shopify/ProductVariant/54020683989299`, Black/L, SKU FSWOA2B.
- Both numeric and GID ingestion aliases were Error. No other orders matched the
  old allocator error in the read-only scan.
- Old function MD5 `1e5f260172220751170863b927f1f2a8`.
- Initial read-only audit SHA256
  `9e15ed654a17b2670c69b032196dc3e7c544c4dba816960017a1cf508eec94d6`.
- Rechecked at 05:20:18 UTC immediately before the authorized repair; allocation
  state remained unchanged.

## Production repair and readback

User explicitly authorized commit, push main and existing Render deployments.
The existing webhook service executed the scoped repair at **12 September 2026,
05:23:08 UTC**. Backup, function installation and allocation were one transaction.
The helper checked product/run/order/variant identity, quantity, paid state,
manual adjustment, empty history/reservations and exact counters under locks.

- Edition order **488**, unit ordinal 1: **#050/100**.
- Edition order **489**, unit ordinal 2: **#051/100**.
- Both retain the exact canonical Shopify order, line, product and variant IDs.
- Both numeric/GID ingestion aliases now Assigned with empty allocation errors.
- Product and active run: **next 52**. Product: **sold 2, remaining 98**, last assigned 51.
- Both allocations valid and identity-enforced, mirror_status synced.
- Normal Orders loader/converter: two rows #050/100 and #051/100, **Needs certificate**.
- Normal Edition Ops loader: next 52, sold 2, remaining 98, enabled true, no sync error.
- Shopify canonical AND legacy metafields read back as next 52, sold 2, remaining 98,
  total 100, enabled true, is_sold_out false, status limited_release.
- Public product page independently reloaded: **NEXT AVAILABLE #052 / 100**,
  NUMBERED EDITION / CERTIFICATE INCLUDED. No template/text was hard-coded.
- No certificates generated/sent; ordinary fulfilment must generate them.
- Post-repair audit found no remaining lines matching the old invariant error.

Backup/audit row: `044d3d3f-85a1-4d00-af1e-5902b4c79301`, repair key
`sc3148-independent-cursor-20260912`. It stores original product/run/order/line
records, adjustments and the previous function definition inside Supabase.
Snapshot SHA256 `3e52492a8c2209c1bf0270708f6cf9fc0ad743d4f78ddc29c4df27fcac6e3a5c`.
The new function MD5 is `9856bdfeb974670ea6bb108cd8614292`.
Readback audit SHA256 `30f8d86431551b8df025e8b421857a1bfcd0260d0b81e7641def22c5f0061e67`.

## Permanent protection

Migration `20260912045939_independent_edition_cursor.sql` replaces only the RPC;
installation does not recalculate product data. Allocation uses the authoritative
locked cursor. Sales increase only by missing units actually committed. Existing
allocations return unchanged on retries, including completed lines after sellout.
Partial legacy retries fill only missing unit ordinals. Numeric/GID source aliases
normalize to one source identity. Variant/product mismatches fail closed.

Existing PostgreSQL advisory transaction locks, product/run FOR UPDATE locks and
source-unit/run-number uniqueness protect multiple lines, variants and concurrent
orders. Bounds, disabled/closed runs, cursor collisions, tombstones and invalid
sales counts remain guarded. No historical number is modified or reused.

Storefront mirroring reads stored Supabase next/sold/remaining independently.
It no longer invents a cursor from sold counts or blocks legitimate manual gaps.
The ingestion-exists shortcut was removed: actual saved allocations decide whether
a paid-line retry is complete. No certificates are generated by webhook repair.

## Validation and release

- 338 focused Python tests in isolated modules: **304 passed, 34 skipped**.
- **17 real PostgreSQL/PLpgSQL scenarios passed**, using PGlite 0.5.8 and the actual
  ledger-write trigger and old/new RPC definitions.
- PGlite serializes submitted calls; it is not a multi-process PostgreSQL stress
  test. Production cross-process exclusion uses the database locks and unique keys.
- Broad combined unittest discovery was attempted and interrupted after shared
  Streamlit form state contaminated unrelated UI tests. Isolated Edition Ops
  editing tests pass (12/12). No unrelated UI code was changed.
- All 11 changed Python files compile; git whitespace checks and Render topology validation pass.
- Audit release: `0521dbfe16d801fd409154e16b1ca1ce025ab2f1`.
- Allocator release: `2ee8b46469d3dc15edfd4e3a391ea991c2b65eba`.
- Ingestion finalization: `15aa7244e2b7c6247c6d815ab0574cf63e177932`.
- Primary service remains sports-cave-os / srv-d8kl4on7f7vs73dvavv0.
- Webhook service remains sports-cave-os-webhooks / srv-d9146onlk1mc739nrm7g.
- Allocator deployment IDs: dep-daie1c95efls738ssoe0 (primary),
  dep-daie1c95efls738sspc0 (webhook), both live.
- Approved production repair deployment: dep-daie2ojm8hqs73cfrib0, live.

Changed files: supabase_backend.py, webhook_server.py, run_migrations.py,
scripts/audit_sc3148.py, scripts/repair_sc3148.py, the new migration,
tests/independent_cursor_postgres.mjs, tests/test_independent_edition_cursor.py,
tests/test_atomic_allocation_incident_repair.py,
tests/test_edition_ops_allocation_integrity.py, tests/test_limited_editions_phase2.py,
tests/test_shopify_sync.py and this report. Earlier audit diagnostics also added
tests/test_sc3148_allocation_diagnostics.py.

NO EXISTING HISTORICAL EDITION NUMBERS WERE CHANGED.

THE ALLOCATOR NO LONGER REQUIRES NEXT_EDITION_NUMBER = SOLD_COUNT + 1.


## Finalization and cleanup

The optional marketplace ingestion columns are absent in this production database.
The finalizer detects that schema and skips those optional fields; it does not add
columns or change unrelated marketplace infrastructure. The authoritative order-line
statuses are Assigned with empty errors. This schema difference does not affect
allocation, certificates, the normal Orders display or Edition Ops.

The temporary write-on-startup incident hook is removed in the final cleanup release.
The narrowly scoped repair/audit scripts remain for auditability; ordinary service
startup only starts the existing reconciliation worker. The temporary MCP connection
probe script and generated protocol directory were removed from the local temp folder.

Final idempotent readback completed at 05:33:56 UTC on 12 September 2026.
Action was `already_repaired`; allocation IDs 488/489 and the complete allocation
history fingerprint `fe5d9c47aa0376af1248603876b9e274` were unchanged.
Order optional ingestion fields were null, with has_ingestion_error false.
Both temporary incident environment flags were disabled after that readback.
