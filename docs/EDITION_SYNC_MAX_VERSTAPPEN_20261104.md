# Max Verstappen product registration incident — 4 November 2026

Studio task: `20261104-6e16adb2`; owner: `codex-max-sync-20261104-01`.
Starting revision and deployed worker: `5fe36f2ca33ad7368c448b7dfbfb81292af16b0e`.

## Evidence

- Shopify product `gid://shopify/Product/15466713841971`, handle
  `max-verstappen-wall-art`, was created at 02:46:39 UTC (13:46:39 Sydney).
- Its only `sports_cave` metafield was `edition_enabled=false`, updated at
  02:51:39 UTC. The available evidence does not identify who or what wrote it.
- Both create/update receipts reached the existing webhook/worker services.
  The worker classified the product as eligible, then registration correctly
  stopped with `explicitly_disabled_mirror_requires_review` / `PendingRegistration`.
  This was not a missing webhook subscription or rejected webhook delivery.
- Authoritative database: Supabase `ceyzbfpuwuuxaiqwiltz`, as documented in the
  existing repository. The similarly named image-factory project has no webhook
  receipts and was not modified.
- A complete paginated Shopify scan found 348 ACTIVE products. Comparing their
  canonical IDs against Edition Ops found exactly one missing product: this one.
- Six other failed receipts refer to product `15440507470131`, which the worker
  reports Shopify can no longer find. Other pending receipts concern inactive
  products, non-wall-art classification, or sport-tag review. These are distinct
  from a missing active Edition Ops product.
- A mass update backlog was present (over 500 received events). The worker was
  actively progressing through its reconciliation scan; this increases latency.
  A theme-related batch may explain the traffic, but causation is not established.

## Authorized operational repair

The user explicitly requested syncing the product and fixing the failure.

1. Read the current Shopify metafield and its compare digest.
2. Changed only `sports_cave.edition_enabled` from `false` to `true`, guarded by
   Shopify compare-and-set. Shopify returned no user errors.
3. Made existing receipt `094d1daf-eeab-5db1-9d58-23965eea5810` due for retry by
   changing only `processed_at` to the epoch. The update was conditional on the
   exact product ID, pending status, and disabled-mirror error. Before the change
   its processed timestamp was `2026-11-04 04:59:03.938623+00`, attempts `8`.
   Retained its payload, attempt history and pending status. The normal worker
   owns registration, sales-history checks, edition-run creation and mirroring.

No ledger counters were inserted/reset manually. No theme, subscription, service,
schema, customer automation or deployment was changed.

## Local scheduling fix, prevention and tests

The worker previously drained ten receipts, then synchronously processed up to
four 50-product reconciliation pages. Live logs showed approximately 20 seconds
per existing product, leaving fresh receipts waiting while a long scan held the
lease. The local change drains one due receipt between scanned products while
retaining the same lease, retry/backoff rules, canonical registration path and
page checkpoint semantics. An isolated PostgreSQL test proves a queued upload
registers before an unrelated scan product, without duplicate edition runs.
This runtime improvement is tested locally and requires explicit commit/release
authorization before deployment. It is not part of the live metadata repair.

Do not write `edition_enabled=false` as an upload placeholder for a product that
is intended to become a numbered edition. This value explicitly disables edition
registration. Leave initialization to the existing onboarding workflow; if an
explicit disabled flag needs correction, review and enable the specific product.
Do not globally ignore disabled/archived metadata: those guards protect historical
editions from accidental reinitialization.

Added an isolated PostgreSQL regression for disabled new-product receipt →
explicit enable → retry of the same durable receipt → one 100-unit edition run,
next number 1, no sales and no duplicate registration.

Validation (synthetic fixtures only, existing Python virtualenv and PGlite):

- `pytest tests/test_shopify_product_onboarding.py -q`: 25 passed.
- `pytest tests/test_product_activation_sync.py tests/test_product_webhook_restoration.py -q`:
  32 passed, 14 subtests passed.
- Existing FastAPI/Starlette deprecation warnings; no test failures.

Local test/document changes remain uncommitted. Final live verification follows
once the existing worker reaches the repaired product.
