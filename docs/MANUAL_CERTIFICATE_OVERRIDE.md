# Manual certificate edition override

The production server runs the reviewed certificate migrations before opening its
port. No live order overrides or customer certificates are created by this repair.

## Operator workflow

1. Select one unallocated, sold-out/expired exception line in Orders as an administrator.
2. Choose **Manual Certificate**, enter the number and reason. The canonical edition size is read-only.
3. If that number is in allocation history, explicitly confirm the duplicate certificate warning.
4. Save. Orders shows **Not allocated · Manual cert #100/100**. Nothing is allocated or generated.
5. Use **Start Fulfilment QA** and complete the existing checks. The existing **Generate + Upload Certificate** action uses the same template and upload workflow.
6. Edit or remove the override before generation. After a certificate record exists, changes are blocked.

This supports the SC3150-style sold-out exception without reopening the edition. The existing conservative identity, administrator, closed-run and unfulfilled-line checks remain in force; mapping/database allocation failures still require repair.

## Storage and isolation

- Reuses `manual_order_line_editions`, separate from the allocation ledger, with its existing `manual-edition:<UUID>` certificate reference.
- Adds `duplicate_confirmed` and an append-only `manual_certificate_audit` table. Insert/edit/remove events contain the actor, timestamp and complete old/new override values, including the reason and stable order/line/product identity. Removal does not remove audit history.
- Existing genuine allocations take priority in the reader. A stale manual reference is rejected if a genuine allocation has since appeared; refreshing selects the genuine allocation.
- Database guards recheck identity, closed state, duplicate confirmation and certificate existence. Certificate generation locks the manual record until certificate persistence completes, preventing concurrent edit/removal.
- QA answers are persisted through the existing dispatch storage before generation, without claiming fulfilment completion. The backend verifies the exact reference, edition number and QA timestamp. An edited override needs fresh QA.
- Manual certificate metadata retains its separate reference through upload. Certificate-only branches skip allocation-table status/metadata writes.
- No changes to the atomic allocator, cursor, reservations, sold/remaining calculations, Edition Ops or canonical Shopify edition metafields. The change in `order_allocator.py` is confined to its Orders display adapter.

## Migration

`migrations/20260912224424_manual_certificate_controls.sql` extends only certificate-override storage and guards. `20260912231446_manual_certificate_identity.sql` adds normalized order/line identity uniqueness without rewriting rows. Both are in the explicit SHA-reviewed deployment manifest in `run_migrations.py`.

The existing primary command, `python sports_cave_server.py`, applies that manifest
before listening. Only unapplied manifest entries run, under a database lock and
one transaction that includes schema verification and tracking. Historic allocator
migrations are excluded. An additional connection verifies committed schema;
failure prevents startup. `python run_migrations.py --deploy --check` validates the
manifest without connecting.

Save now commits and rereads the exact override on a new connection before
reporting success. Numeric and GID aliases share a unique database identity.
Removal is also verified on a fresh connection. Orders reloads the authoritative
row and checks source, order, line and product identity. Errors do not set a fake
success value in session state.

The production gap was confirmed in Render settings: the primary pre-deploy
command applied only `20260901_os_repair_requests.sql`. Neither primary startup
nor webhook startup applied the certificate migration. Logs at 23:03 and 23:08 UTC
on 12 September nevertheless show the resolver reading an existing SC3150 manual
record and blocking on QA; they do not demonstrate deletion of that record.

## Local validation

- 132 focused backend/certificate/Orders/ledger/deployment tests passed, including 12 persistence/deployment regressions.
- 7 Orders/Fulfilment loading tests and 8 Supabase tests passed.
- Broader Orders UI module: 136 passed; one existing unrelated Mockups source assertion failed (`test_mockups_prompt_cards_use_compact_modal_prompt_actions`). `app.py` is unchanged.
- 12 isolated PostgreSQL/PGlite checks passed, including duplicate confirmation, normalized identity, database restart persistence, schema catalogue validation, audit immutability, edit/remove locks and byte-for-byte unchanged allocation history/counters.
- Changed Python files compile; `git diff --check` passes.

No live SC3150 override is entered by deployment and no customer certificate is generated. Local tests use fixtures/mocks and isolated PostgreSQL only. Nathan can test the normal Manual Certificate → refresh → Fulfilment QA → Generate + Upload workflow after deployment.
