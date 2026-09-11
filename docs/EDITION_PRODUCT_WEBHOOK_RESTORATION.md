# Edition product webhook restoration — local verification

Date: 2026-09-12. No push, deployment, production subscription changes, migrations,
or production edition/order/certificate writes were performed.

## Findings

The product webhook implementation was not removed. Git commit `362a309` introduced
the product update route; both product routes, backend processor, and GraphQL
subscription helpers remain in the current tree. Registration is an explicit action
in the existing developer tools UI, not a Render startup step. `0c5e81f` deliberately
deferred Shopify metafield mirroring and introduced the pending-configuration label;
it did not remove Supabase initialization at #1.

Confirmed repository defects:

- `_hydrate_from_snapshot_once` returned forever after the first session load,
  bypassing the existing 180-second Supabase display cache expiry. Webhook inserts
  could therefore remain invisible in an open Edition Ops session.
- Product sync treated DRAFT as eligible for edition initialization.
- `_apply_edition_product_incremental_plan` called the global
  `_ensure_active_edition_runs_for_products`, whose UPDATE copies run counters over
  every edition product. A stale run could overwrite authoritative product state.
- Concurrent product deliveries could both observe a missing row before insertion.
  There was no explicit orphaned-history guard.
- Product database processing ran on the FastAPI event loop, blocking other requests
  including health checks while processing.

These are code-confirmed findings, not a diagnosis of production delivery.
Live subscriptions, delivery failures, production HMAC configuration, and deployed
revision were not inspected. It is not established that subscriptions are missing
or that the observed manual-number symptom was caused by any particular live event.

## Architecture and behavior

The existing `sports-cave-os-webhooks` FastAPI service still handles:

- `orders/paid` at `/webhooks/shopify/orders-paid` (unchanged).
- `products/create` at `/webhooks/shopify/products-create`.
- `products/update` at `/webhooks/shopify/products-update`.

Both product topics are required. No publication topic or second webhook service
is added: ACTIVE is the repository's eligibility convention. This does not separately
require Online Store publication; active products on other channels remain eligible.

The product flow is raw-body HMAC validation → durable `webhook_events` receipt →
product normalization → ACTIVE filter → shared product sync transaction → Supabase
`shopify_products`/variants metadata and `edition_products` → normal Edition Ops reader.
Database operations now use the existing thread-pool pattern; successful responses
still wait for persistence rather than acknowledging an undurable background task.

DRAFT creation records a skipped receipt without creating an edition product.
A subsequent ACTIVE products/update delivery initializes it, without needing to
remember the earlier draft or its creation timestamp.

New rows use the existing defaults: `edition_total=100`, `next_edition_number=1`,
`last_assigned_edition=0`, `sold_count=0`, `remaining_count=100`. Only newly inserted
rows receive a new active run. Supabase is authoritative; Shopify mirror status is
still separate and does not gate Edition Ops visibility or require typing 1.

## Existing-state protection and idempotency

Existing records are matched by Shopify GID/numeric identity, then the existing safe
legacy handle/title rules. Identity conflicts fail closed. Metadata UPDATE statements
allow only identity/title/image/raw fields and timestamps; they cannot assign edition
counters, limits, sold-out flags, or manual active/inactive overrides. Run metadata
updates likewise do not touch counters. No order, allocation, certificate, or existing
audit rows are changed.

The shared transaction locks `edition_products` in SHARE ROW EXCLUSIVE mode before
identity lookup, serializing creation and metadata writes across processes/restarts.
Existing database uniqueness remains in force. The lock can briefly delay other
edition writes during a sync; no external Shopify requests occur while it is held.
Durable webhook receipts suppress completed redelivery, and failed events remain
retryable. Apply errors roll back before commit. Tests model concurrency at the
database boundary; this was not a live PostgreSQL concurrency/load test.

Before inserting a missing product, the transaction checks `edition_orders`,
`edition_runs`, and `edition_allocation_tombstones` by identity/handle. Existing history
causes an error for review, never reconstruction at #1. The current ledger schema
must already exist; missing history tables fail closed, and no migration is run.

Both Pull New Products and full manual product reconciliation already used the shared
helper and retain it. Full reconciliation no longer invokes global schema/run
backfills. The repaired product sync paths cannot reset an existing product to #1:
the #1 assignment is confined to guarded INSERT, never existing-row UPDATE.

Edition Ops now respects the existing display cache TTL on normal page reruns.
An already open page refreshes on the next rerun after expiry (default 180 seconds);
an idle browser does not receive a push refresh. Unsaved editor changes defer refresh.
No polling job, new sync button, broad cache reset, or page redesign was added.

## Local files

- `supabase_backend.py`: eligibility, safe creation, history/transaction guards, scoped runs.
- `webhook_server.py`: payload validation, product logging, thread-pool processing.
- `edition_ops.py`: session snapshot expiry with edit protection.
- `scripts/register_shopify_product_webhooks.py`: inspect-first registration using existing helpers.
- `tests/test_product_webhook_restoration.py`: 13 focused regression tests.
- `tests/test_shopify_sync.py`: existing cursor fixtures support the transaction lock.
- This report. Pre-existing unrelated mockup test changes were left intact.

## Verification

The 13 new tests cover new ACTIVE initialization and normal loader visibility,
existing #53 plus stale-run/manual-override protection, unrelated existing products,
duplicate/concurrent delivery, DRAFT → ACTIVE, existing/orphaned history, both manual
sync paths, rollback, actual HMAC rejection/acceptance, responsive health checks,
display refresh/edit preservation, and inspect-only registration.

Final regression runs: 318 tests in the backend/product/edition suites with 34
existing retired-allocator skips; 12 Edition Ops table-editing tests passed separately.
Total: 296 passed, 34 skipped. The combined single-process run exposed an existing
Streamlit form-context test-isolation failure. That AppTest failure was reproduced
with the original HEAD UI implementation; running its module separately passes.

All six changed Python files pass `py_compile`; `git diff --check` passes.
Tests use fixtures/mocks/local test data; production PostgreSQL behavior and actual
Shopify delivery still need an approved production validation step.

## Registration after explicit approval

Production topic registration remains **unverified**, not presumed absent.
Set `SPORTS_CAVE_WEBHOOK_BASE_URL` to the confirmed existing webhook service base URL
and use the existing Shopify credentials in the approved environment. The script
requires this explicit base URL rather than falling back to the main app.

Inspect without changing subscriptions:

```powershell
.venv\Scripts\python.exe scripts/register_shopify_product_webhooks.py
```

Only after explicit approval and deployment of the local repair, create missing
subscriptions using the existing registration helpers (no deletions):

```powershell
.venv\Scripts\python.exe scripts/register_shopify_product_webhooks.py --apply
```

Neither command was executed against production in this task.

**SAFE FOR NATHAN TO TEST LOCALLY: YES**, using the fixture-based regression tests.
This is not a claim of live deployment or verified production delivery.
