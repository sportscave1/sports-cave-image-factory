# Edition Ops complete recovery (local implementation)

## Confirmed code gap
The primary Pull New Products button called `sync_new_shopify_products_to_edition_ops`, whose `created_at` watermark cannot discover an older Draft activated after that watermark. The separate complete catalogue path was already available in Advanced controls. The user supplied the production no-row/no-receipt evidence; this change made no production inspection or writes.

## Repair
The primary button now calls `reconcile_all_shopify_products_to_edition_ops`. Existing Shopify pagination has no created-time cutoff and fails explicitly on incomplete pagination. Candidates pass the canonical Shopify ID refetch and existing ACTIVE/published/Sports Cave/Framed Art/collector classifier. Excluded products remain excluded. Missing classification/publication candidates are reported for review.

Full reconciliation calls `register_shopify_products_for_edition_ops` with `missing_only=True`. The existing table lock serializes identity lookup and insertion; stable GID/ID and legacy identity protections remain intact. Existing rows are skipped entirely. New-row history checks reject allocations, orphan runs, tombstones and historical mirror evidence. Only inserted rows obtain their existing canonical defaults and active run. Ambiguous/history failures fail closed transactionally, with the product-specific error; they are never treated as an empty successful discovery.

The committed registration's Pending automatic mirror marker is retained until the existing canonical mirror writes and fresh namespace/key/value readback agrees. The locked ledger supplies values, never inventory. Manual mirror failures are reported per product while other pending mirrors continue. A later reconciliation retries only pending registrations. Webhooks still raise on mirror failure so delivery retry remains effective. A closed/disabled ledger is never reopened by this initializer.

Unsaved editor changes block reconciliation until saved/discarded. After reconciliation the UI reloads Supabase and displays checked/added/unchanged/verified/pending/issues counts, with individual errors. Normal page reruns perform no full Shopify scan.

## Existing webhook architecture / operator follow-up
Both `/webhooks/shopify/products-create` and `/webhooks/shopify/products-update` use existing HMAC validation and canonical registration/refetch. The existing registration script is inspect-only by default, app-scoped, and never removes subscriptions.

After approved deployment, from the configured OS environment (not a different connector app):

```
python scripts/register_shopify_product_webhooks.py --receipts
```

This reads expected/observed callbacks and topic subscriptions, existing product diagnostics and latest successful/failed receipts, without schema maintenance. The configured `SPORTS_CAVE_WEBHOOK_BASE_URL` must be the existing supporting webhook service. HMAC rejections before receipt insertion remain visible in Render request logs, not necessarily the DB receipt table. No production subscription health has been asserted from local tests.

Then use Edition Ops **Pull New Products** once to recover missed activations, including the supplied Perkins/Ingall example if its current canonical state remains eligible and history-free. No individual product is hardcoded in application logic. Subscribe missing topics only after a separate approved production action. No new scheduled polling job was added; recovery still requires delivery of a webhook or an operator reconciliation.

## Storefront scope
The managed `shopify/` and `shopify_theme/` snippets do not contain the reported `EDITION ARCHIVED / COLLECTOR RUN CLOSED` wording. No theme source was changed. In the separately managed live theme, locate that branch and distinguish missing required edition metafields (neutral `EDITION TEMPORARILY UNAVAILABLE`) from explicit archived/closed/disabled ledger mirror state (retain archived wording). Check field presence before converting defaults to booleans/numbers; absence must not be interpreted as false/closed. This remains a separate theme review, not a completed production fix.

## Upload Live contract
Only the Live finalisation prompt now requires exact-ID Edition Ops/run/mirror verification through the existing service. An exported execution environment without access must report `EDITION OPS READINESS UNVERIFIED`; ACTIVE is not proof of operational completion. Draft contract and product copy are unchanged. No upload-side allocation logic was added.

## Validation
288 focused Edition Ops, activation, webhook, Shopify sync, recovery and product-upload tests ran: 254 passed, 34 skipped. Stateful SQL doubles exercise the real registration planner/write/run paths, but are not production PostgreSQL integration tests. Python compilation and git diff --check passed. No migration is required.


## Final eligibility cleanup
The mandatory modern-tag gate was a second discovery defect: it rejected valid legacy Framed Art and reclassified existing ledgers. The shared rule is now ACTIVE + Online Store publication + Sports Cave vendor + Framed Art, subject to all existing explicit exclusions. Collector Series / Limited Edition tags and collection membership are not prerequisites. A single optional `edition-exempt` tag explicitly opts a missing product out; it does not change an existing ledger.

Full reconciliation bulk-loads stable Shopify identities before classifying or refetching candidates. Internal database row IDs are never treated as Shopify IDs. Existing identities are counted unchanged and skipped. Only an existing Pending automatic mirror marker retains the established committed-ledger retry path. The write transaction still rechecks identity/history under its original lock, including races after the bulk read.

Explicit exclusions (internal/private/hidden/upsell/test/apparel/certificate/fulfilment and configured certificate identities), wrong vendor, non-Framed Art and Draft are quiet exclusions. Missing/uncertain publication or an invalid canonical response remains actionable. The summary separates excluded products; details appear in a collapsed review expander. The canonical new-row/run defaults and allocator are unchanged.

Regression fixtures cover 180 existing untagged products plus three missing untagged products: 180 unchanged, three inserted/mirrored, zero review errors; a repeated run inserts/mirrors nothing. Existing sold and archived rows and orphan-history guards remain tested. Products/create and products/update use the same updated rule; a no-tag Draft to Active canonical refetch registers correctly.

After an approved deployment, run one normal Pull New Products reconciliation. No live run, tag edits or production inspection were performed here. No migration is required.
