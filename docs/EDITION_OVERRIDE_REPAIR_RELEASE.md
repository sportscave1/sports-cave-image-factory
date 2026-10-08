# Edition Ops manual override repair — 8 October 2026

## Status and cause

Implemented and rehearsed locally; **not production-ready yet**. No production
migration, deployment, edition change, or Shopify write was performed.

The deployed save path required `override_edition_cursor`, but its migration and
two dependencies were absent from `DEPLOYMENT_MIGRATIONS`. Read-only inspection
found no override function in either accessible Supabase project. Render's
canonical `sports-cave-os` service (`srv-d8kl4on7f7vs73dvavv0`) currently has the
pre-deploy command `python run_migrations.py --only 20260901_os_repair_requests.sql`.
Its `sports_cave_server.py` startup also runs the reviewed deployment manifest,
which previously omitted this chain. Workers do not install it themselves.
Casting the original seven parameters could not repair the missing function.

The prior UI also submitted reconciliation-marked rows without explicit edits
and could fall back to the older batch save. The old function rejected historical
counter inconsistencies and number reuse. These are separate from the missing
schema and are addressed by the follow-up migration and changed-row-only UI.

## Scope

- Six visible columns: product, next edition number, edition limit, sync status,
  Shopify Admin link, live product link. Existing virtualized scrolling remains.
- One schema preflight per save batch, no DDL during page rendering or Save, and
  no fallback. Failure retains edits and produces one compact message.
- Only changed cursor/limit rows are submitted. Stable request IDs, expected
  cursor/limit checks, administrator verification, and the allocator's product
  advisory lock protect retries and concurrent orders.
- Administrator saves can lower/reuse a number without another confirmation.
  No release is created. Audit records contain before/after cursor and limit.
- Historical orders, certificates and sold counts are not rewritten. Cursor-only
  edits preserve remaining count too. An explicit limit change updates available
  capacity from that new limit and the unchanged sold count.
- New purchases still enforce sales caps and unique order-line identities.
- Existing persisted override guards prevent reconciliation from replacing the
  cursor. Shopify publication ignores historical cursor-boundary diagnostics for
  an authorized override, but retains cursor consistency and availability checks.
- Existing durable pending jobs and bounded retry infrastructure are reused.
  The background accelerator starts after DB commit. No new services or polling
  infrastructure were introduced.

## Shopify contract

The existing product-owner write updates `sports_cave.edition_next_number`, the
legacy `sports_cave.next_edition_number`, and the existing compatible edition
display/counter fields. Values come from authoritative database fields; sales
are not inferred from cursor minus one. The existing compare-digest write and
independent readback must both succeed before the database records `Synced`.
Failed writes/readbacks retain the saved cursor and retry state. The table and
compact status panel never treat a confirmed database save as confirmed Shopify
publication. Actual storefront verification remains a release acceptance step.

## Migration order and prerequisites

The reviewed deployment manifest and targeted `--edition` runner now include:

1. `20261008041452_edition_version_transitions.sql`
2. `20261008045733_edition_version_guard_hardening.sql`
3. `20261008065000_explicit_edition_cursor_override.sql`
4. `20261008090000_edition_admin_cursor_repair.sql`

Existing prerequisites are the current edition products/runs/orders schema,
UUID `os_users.id`, allocation tombstones, and the deployed independent-cursor
atomic allocator. Do not replay historical allocator/repair migrations over a
live database. The chain fails transactionally if required allocator anchors are
absent. All four files have pinned SHA-256 review entries.

The new typed callable is:
`public.override_edition_cursor(text,uuid,integer,integer,uuid,uuid,integer,integer)`.
The original seven-argument callable remains as a compatibility wrapper.
The only additional audit columns are `previous_limit` and `next_limit`.
Historical rows remain intact. New function execution is revoked from public,
anonymous and authenticated API roles; the existing trusted backend performs
the administrator check. Normal RLS and allocation protections remain.

## Authorized release procedure — not executed

1. Obtain explicit production release authorization. Confirm the **actual**
   canonical web service and matching reconciliation worker `DATABASE_URL`
   point to the same intended Supabase project. Do not choose by project name.
   Read-only discovery saw two projects; the Render environment-to-project
   mapping could not be conclusively verified in this session.
2. Take and verify a secure schema backup plus data backups of edition products,
   runs, orders, certificates, tombstones, version audit, cursor override audit
   (if installed), and migration ledger. Confirm a recovery/PITR point. Do not
   put customer backups or credentials in this repository.
3. Restore the affected schema to staging and rehearse the chain there. Local
   PostgreSQL testing used synthetic tables matching inspected types and a
   read-only capture of the deployed allocator; it was not a full production
   backup restore. Check constraints/indexes and existing migration ledger for
   drift before proceeding.
4. From this reviewed release, with the existing secure database environment,
   validate without connecting:

   ```sh
   python run_migrations.py --edition --check
   python run_migrations.py --deploy --check
   python scripts/validate_render_topology.py
   ```

5. After confirming the target and backup, run the targeted database migration
   **before** releasing the new UI and matching worker code:

   ```sh
   python run_migrations.py --edition --expected-project <verified-project-ref>
   python run_migrations.py --verify-edition-schema --expected-project <verified-project-ref>
   ```

   The runner verifies reviewed hashes, takes the deployment advisory lock,
   applies unrecorded files in one transaction, records them, commits, and then
   opens a fresh read-only connection to verify the exact function signature and
   all four migration records. Replaying the command is a ledger no-op. Remote
   target checking requires an exact project component in the Supabase host or
   pooler username. Never substitute another project's URL to bypass a failure.
6. Release the existing web service and matching order-reconciliation workers
   using the normal workflow. Startup now includes the verified edition chain;
   the existing pre-deploy command alone is not sufficient. Do not create or
   rename services. No `render.yaml` or Render plan change is needed.
7. Verify the schema from the app/worker environments. On an approved staging
   product, perform a single Save & Sync, independent Shopify readback, worker
   restart, and storefront refresh. Confirm `005`, unchanged sold quantities,
   and accurate Pending/Failed/Synced transitions. Only an explicit authorized
   administrator save may change a real product number.
8. Stop rollout on schema or readback mismatch; retain Pending/Failed status.
   Do not write Shopify directly around a DB failure. Keep historical/audit
   migrations intact; use a reviewed forward fix rather than dropping ledger
   tables to roll back.

## Verification and limits

- Actual PostgreSQL **17.6** on loopback, fresh isolated databases: chain install,
  independent post-commit verification, and repeated runner replay passed.
- Focused Edition suite: **88 tests passed**, including synthetic reported product
  cases/numbers 001/005/050/095/100, 95→5 with sold94/remaining6, limit changes,
  preserved certificates, cap enforcement, order/admin concurrency, retries,
  missing schema, failed input retention, readback mismatch, and Streamlit saves.
- **16 migration/startup checks passed** separately. The final UI run passed
  **17 tests**, including the added compact sync-summary/error-redaction test
  (the remaining UI cases repeat coverage in the 88-test suite). Python compile,
  both reviewed manifest checks, Git whitespace checks, and Render topology
  validation passed. There is no separate frontend production bundle for these
  Python/Streamlit changes.
- Browser fixture: 500 continuously scrollable rows; search and archive caused
  zero full-app reruns. No oversized icons, missing table frames, page errors,
  or horizontal page overflow at 1440/1000/750/390px widths.
- Measured local fixture: initial table 523ms; warm return 266ms; search 274ms;
  dialog 209ms; archive 130ms. Search added zero catalog loads. These include
  browser automation overhead and mocked data, not production latency. No
  comparable current-production before measurement was available, so no speedup
  percentage is claimed.
- App-startup contract tests are run separately: importing the full app before
  Streamlit AppTest contaminates its form context when combined in one process.
  The focused browser and AppTest workflows pass in isolation.
- Production database installation, target confirmation, backup restore rehearsal,
  and real Shopify/storefront sync remain release gates. No customer email, order,
  certificate or live product was changed during this work.

Implementation files: `edition_cursor_overrides.py`, `edition_version_ui.py`,
`edition_ops.py`, `supabase_backend.py`, `run_migrations.py`, the new repair SQL.
Test/rehearsal support: `scripts/rehearse_edition_postgres.py`,
`tests/edition_db_fixture.py`, `tests/edition_postgres_server.mjs`,
`tests/fixtures/edition_live_allocator_20261008.sql`,
`tests/fixtures/edition_workspace.py`, and the updated edition/migration tests.
